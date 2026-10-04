"""Evidence normalization, PDF generation and transaction compensation."""
import base64
import binascii
import hashlib
import io
import logging
from html import escape

from fastapi import HTTPException
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import event
from sqlalchemy.orm import Session

from ..core.utils import local_now
from ..models import DeliveryStatus
from . import object_storage

logger = logging.getLogger(__name__)
MAX_PHOTO_BYTES = 12_000_000


def normalize_image(value, kind):
    limit = 1_500_000 if kind == 'signature' else MAX_PHOTO_BYTES
    try:
        header, encoded = value.split(',', 1)
        allowed = {'data:image/png;base64': 'PNG'} if kind == 'signature' else {
            'data:image/png;base64': 'PNG', 'data:image/jpeg;base64': 'JPEG', 'data:image/webp;base64': 'WEBP'}
        if header not in allowed or len(encoded) > (limit + 2) // 3 * 4:
            raise ValueError()
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > limit:
            raise ValueError()
        with Image.open(io.BytesIO(raw)) as image:
            max_pixels = 4_000_000 if kind == 'signature' else 24_000_000
            if image.format != allowed[header] or image.width * image.height > max_pixels or getattr(image, 'n_frames', 1) != 1:
                raise ValueError()
            image.load()
            image = ImageOps.exif_transpose(image)
            image.thumbnail((1600, 1600) if kind != 'signature' else (2000, 1000))
            # Flatten transparency and strip EXIF/GPS/other untrusted metadata.
            canvas = Image.new('RGB', image.size, 'white')
            if 'A' in image.getbands():
                canvas.paste(image.convert('RGB'), mask=image.getchannel('A'))
            else:
                canvas.paste(image.convert('RGB'))
            out = io.BytesIO()
            canvas.save(out, format='PNG' if kind == 'signature' else 'JPEG', **({} if kind == 'signature' else {'quality': 82, 'optimize': True}))
            return out.getvalue()
    except (ValueError, binascii.Error, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(400, 'Immagine non valida: firma PNG, foto JPEG/PNG/WebP, massimo 12 MB e 24 megapixel') from None


def evidence_metadata(status):
    return {
        'has_signature': bool(status and (status.signature_object_key or status.signature_data)),
        'has_delivery_photo': bool(status and status.delivery_photo_object_key),
        'has_pod': bool(status and status.pod_object_key),
    }


def _cleanup(entries):
    for storage, key in entries:
        try:
            storage.delete(key)
        except Exception:
            logger.error('POD cleanup failed for evidence key %s; reconciliation required', key)


@event.listens_for(Session, 'after_rollback')
def rollback_evidence(db):
    _cleanup(db.info.pop('pod_new_objects', []))
    db.info.pop('pod_old_objects', None)


@event.listens_for(Session, 'after_commit')
def commit_evidence(db):
    db.info.pop('pod_new_objects', None)
    _cleanup(db.info.pop('pod_old_objects', []))


def commit_delivery_update(db):
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def store_evidence(db, storage, route, delivery, status, kind, raw, content_type):
    key = object_storage.object_key(route.user_id, route.id, delivery.id, kind)
    # Register before upload: a timed-out PUT may have succeeded remotely.
    db.info.setdefault('pod_new_objects', []).append((storage, key))
    storage.upload(key, raw, content_type)
    old = getattr(status, kind + '_object_key')
    if old:
        object_storage.validate_key(old, route.user_id, route.id, delivery.id, kind)
        db.info.setdefault('pod_old_objects', []).append((storage, old))
    setattr(status, kind + '_object_key', key)
    setattr(status, kind + '_size', len(raw))
    setattr(status, kind + '_sha256', hashlib.sha256(raw).hexdigest())
    if kind != 'pod':
        setattr(status, kind + '_content_type', content_type)


def read_evidence(storage, route, delivery, status, kind):
    key = getattr(status, kind + '_object_key')
    if not key:
        if kind == 'signature' and status.signature_data:
            return normalize_image(status.signature_data, 'signature')
        return None
    object_storage.validate_key(key, route.user_id, route.id, delivery.id, kind)
    raw = storage.read(key)
    if hashlib.sha256(raw).hexdigest() != getattr(status, kind + '_sha256'):
        raise object_storage.unavailable()
    return raw


def _pod_datetime(value):
    if not value:
        return "-"
    try:
        return value.strftime("%d/%m/%Y · %H:%M")
    except Exception:
        return str(value)


def _pod_company_address(owner):
    parts = []
    address = (getattr(owner, "company_address", None) or getattr(owner, "company_legal_address", None) or "").strip()
    if address:
        parts.append(address)
    locality = " ".join(filter(None, [
        (getattr(owner, "company_zip", None) or "").strip(),
        (getattr(owner, "company_city", None) or "").strip(),
    ])).strip()
    if locality:
        parts.append(locality)
    country = (getattr(owner, "company_country", None) or "").strip()
    if country and country.lower() != "italia":
        parts.append(country)
    return ", ".join(parts)


def _pod_logo_bytes(value):
    """Accept only embedded company logos; never fetch remote URLs while closing a delivery."""
    if not value or not isinstance(value, str) or not value.startswith("data:image/"):
        return None
    try:
        header, encoded = value.split(",", 1)
        allowed = {
            "data:image/png;base64": "PNG",
            "data:image/jpeg;base64": "JPEG",
            "data:image/webp;base64": "WEBP",
        }
        expected = allowed.get(header)
        if not expected or len(encoded) > 2_000_000:
            return None
        raw = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != expected or image.width * image.height > 8_000_000 or getattr(image, "n_frames", 1) != 1:
                return None
            image.load()
        return raw
    except Exception:
        return None


def _draw_wrapped_pdf_text(pdf, text, x, y, width, *, font="Helvetica", size=8.4,
                           color=None, leading=None, max_lines=2, ellipsis=True):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.lib import colors

    value = " ".join(str(text or "-").replace("\n", " ").split())
    words = value.split(" ") if value else ["-"]
    leading = leading or (size + 2)
    lines, current = [], ""
    for word in words:
        trial = word if not current else current + " " + word
        if stringWidth(trial, font, size) <= width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) >= max_lines:
            break
    if len(lines) < max_lines and current:
        lines.append(current)

    consumed = " ".join(lines)
    if ellipsis and consumed != value and lines:
        last = lines[-1]
        while last and stringWidth(last + "…", font, size) > width:
            last = last[:-1]
        lines[-1] = (last.rstrip() + "…") if last else "…"

    pdf.setFont(font, size)
    pdf.setFillColor(color or colors.HexColor("#0F172A"))
    for line in lines[:max_lines]:
        pdf.drawString(x, y, line)
        y -= leading
    return y


def _draw_contained_image(pdf, raw, x, y, width, height, *, padding=8, background=True):
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader

    if background:
        pdf.setFillColor(colors.white)
        pdf.roundRect(x, y, width, height, 8, fill=1, stroke=0)
    if not raw:
        pdf.setFillColor(colors.HexColor("#94A3B8"))
        pdf.setFont("Helvetica", 8.5)
        pdf.drawCentredString(x + width / 2, y + height / 2, "Non acquisita")
        return

    try:
        reader = ImageReader(io.BytesIO(raw))
        iw, ih = reader.getSize()
        available_w = max(1, width - 2 * padding)
        available_h = max(1, height - 2 * padding)
        scale = min(available_w / iw, available_h / ih)
        dw, dh = iw * scale, ih * scale
        dx = x + (width - dw) / 2
        dy = y + (height - dh) / 2
        pdf.drawImage(reader, dx, dy, dw, dh, preserveAspectRatio=True, mask="auto")
    except Exception:
        pdf.setFillColor(colors.HexColor("#94A3B8"))
        pdf.setFont("Helvetica", 8.5)
        pdf.drawCentredString(x + width / 2, y + height / 2, "Anteprima non disponibile")


def generate_pod(route, delivery, status, owner, signature=None, photo=None):
    """Generate a compact, branded, single-page A4 proof of delivery."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4, pageCompression=1)
    page_w, page_h = A4

    navy = colors.HexColor("#0F172A")
    blue = colors.HexColor("#2563EB")
    blue_dark = colors.HexColor("#1746A2")
    blue_soft = colors.HexColor("#EFF6FF")
    border = colors.HexColor("#D7E3F4")
    muted = colors.HexColor("#64748B")
    light = colors.HexColor("#F8FAFC")
    green = colors.HexColor("#168B59")
    green_soft = colors.HexColor("#EAF8F1")
    line = colors.HexColor("#E2E8F0")
    white = colors.white

    left = 15 * mm
    right = page_w - 15 * mm
    content_w = right - left

    # --- Header / GiroFacile brand -------------------------------------------------
    brand_y = page_h - 20 * mm
    icon = 11 * mm
    pdf.setFillColor(blue)
    pdf.roundRect(left, brand_y - icon + 1.5 * mm, icon, icon, 3 * mm, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawCentredString(left + icon / 2, brand_y - 4.2 * mm, "G")

    word_x = left + icon + 4 * mm
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(word_x, brand_y - 1 * mm, "Giro")
    giro_w = pdf.stringWidth("Giro", "Helvetica-Bold", 18)
    pdf.setFillColor(blue)
    pdf.drawString(word_x + giro_w, brand_y - 1 * mm, "Facile")

    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 23)
    pdf.drawString(left, brand_y - 14 * mm, "Prova di consegna")
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 9.5)
    pdf.drawString(left, brand_y - 20 * mm, "Documento di avvenuta consegna")

    # Company identity card, based on the company's saved profile.
    company_w = 75 * mm
    company_h = 29 * mm
    company_x = right - company_w
    company_y = page_h - 44 * mm
    pdf.setFillColor(blue_soft)
    pdf.roundRect(company_x, company_y, company_w, company_h, 4 * mm, fill=1, stroke=0)

    logo_raw = _pod_logo_bytes(getattr(owner, "company_logo_url", None))
    logo_box = 17 * mm
    logo_x = company_x + 5 * mm
    logo_y = company_y + company_h - logo_box - 5 * mm
    if logo_raw:
        _draw_contained_image(pdf, logo_raw, logo_x, logo_y, logo_box, logo_box, padding=2, background=False)
    else:
        initials = "".join(part[:1] for part in (getattr(owner, "company_name", None) or owner.username or "A").split()[:2]).upper() or "A"
        pdf.setFillColor(colors.HexColor("#DBEAFE"))
        pdf.circle(logo_x + logo_box / 2, logo_y + logo_box / 2, logo_box / 2, fill=1, stroke=0)
        pdf.setFillColor(blue_dark)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawCentredString(logo_x + logo_box / 2, logo_y + logo_box / 2 - 3, initials)

    company_text_x = logo_x + logo_box + 4 * mm
    company_text_w = company_x + company_w - company_text_x - 4 * mm
    company_name = getattr(owner, "company_name", None) or owner.username or "Azienda"
    _draw_wrapped_pdf_text(pdf, company_name, company_text_x, company_y + company_h - 7 * mm,
                           company_text_w, font="Helvetica-Bold", size=10.5, max_lines=1)
    company_info_y = company_y + company_h - 13 * mm
    company_address = _pod_company_address(owner)
    if company_address:
        company_info_y = _draw_wrapped_pdf_text(pdf, company_address, company_text_x, company_info_y,
                                                company_text_w, size=7.4, color=muted, max_lines=2)
    vat = (getattr(owner, "company_vat", None) or "").strip()
    if vat:
        company_info_y = _draw_wrapped_pdf_text(pdf, f"P. IVA {vat}", company_text_x, company_info_y - 0.5 * mm,
                                                company_text_w, size=7.4, color=muted, max_lines=1)
    contact = " · ".join(filter(None, [
        (getattr(owner, "company_phone", None) or "").strip(),
        (getattr(owner, "company_email", None) or getattr(owner, "email", None) or "").strip(),
    ]))
    if contact:
        _draw_wrapped_pdf_text(pdf, contact, company_text_x, company_info_y - 0.5 * mm,
                               company_text_w, size=7.1, color=muted, max_lines=1)

    # --- Status banner -------------------------------------------------------------
    status_y = page_h - 67 * mm
    status_h = 20 * mm
    pdf.setFillColor(green_soft)
    pdf.roundRect(left, status_y, content_w, status_h, 4 * mm, fill=1, stroke=0)
    pdf.setFillColor(green)
    pdf.circle(left + 8 * mm, status_y + status_h / 2, 5 * mm, fill=1, stroke=0)
    pdf.setStrokeColor(white)
    pdf.setLineWidth(1.8)
    pdf.line(left + 5.5 * mm, status_y + 10 * mm, left + 7.4 * mm, status_y + 8.1 * mm)
    pdf.line(left + 7.4 * mm, status_y + 8.1 * mm, left + 11 * mm, status_y + 12.2 * mm)

    pdf.setFillColor(green)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(left + 16 * mm, status_y + 12 * mm, "Consegna completata")
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(left + 16 * mm, status_y + 6.5 * mm, "La consegna è stata registrata con successo.")

    divider_x = right - 64 * mm
    pdf.setStrokeColor(colors.HexColor("#CFE9DC"))
    pdf.line(divider_x, status_y + 4 * mm, divider_x, status_y + status_h - 4 * mm)
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(divider_x + 6 * mm, status_y + 12.5 * mm, "Data e ora consegna")
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(divider_x + 6 * mm, status_y + 7.2 * mm, _pod_datetime(status.completata_il))
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 6.8)
    pdf.drawString(divider_x + 6 * mm, status_y + 3.2 * mm, "Europe/Rome")

    # --- Details -------------------------------------------------------------------
    details_y = page_h - 146 * mm
    details_h = 72 * mm
    pdf.setFillColor(white)
    pdf.setStrokeColor(border)
    pdf.setLineWidth(0.7)
    pdf.roundRect(left, details_y, content_w, details_h, 4 * mm, fill=1, stroke=1)

    header_h = 13 * mm
    pdf.setFillColor(blue_soft)
    pdf.roundRect(left, details_y + details_h - header_h, content_w, header_h, 4 * mm, fill=1, stroke=0)
    pdf.setFillColor(blue_dark)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left + 6 * mm, details_y + details_h - 8.5 * mm, "Dettagli consegna")

    driver = route.driver
    vehicle = route.vehicle
    driver_name = " ".join(filter(None, [getattr(driver, "nome", None), getattr(driver, "cognome", None)])) if driver else "-"
    vehicle_name = f'{getattr(vehicle, "nome", "") or ""}'
    if vehicle and getattr(vehicle, "targa", None):
        vehicle_name += f' / {vehicle.targa}'
    vehicle_name = vehicle_name or "-"

    left_rows = [
        ("Azienda", company_name),
        ("Giro", f'{route.id} - {route.nome or "Giro consegne"}'),
        ("Consegna", str(delivery.id)),
        ("Cliente", delivery.cliente_nome or "-"),
        ("Indirizzo", delivery.indirizzo or "-"),
    ]
    right_rows = [
        ("Autista", driver_name),
        ("Mezzo / targa", vehicle_name),
        ("Colli / peso kg", f'{delivery.colli or 0} / {delivery.peso_kg or 0}'),
        ("Firmatario", status.signed_by_name or "-"),
        ("Data firma", _pod_datetime(status.signed_at)),
    ]

    col_gap = 8 * mm
    col_w = (content_w - col_gap) / 2
    col2_x = left + col_w + col_gap
    body_top = details_y + details_h - header_h - 4 * mm
    row_h = 10.5 * mm
    pdf.setStrokeColor(line)
    pdf.line(left + col_w + col_gap / 2, details_y + 5 * mm, left + col_w + col_gap / 2, body_top + 1 * mm)

    def draw_detail_column(rows, x):
        for idx, (label, value) in enumerate(rows):
            ry = body_top - idx * row_h
            if idx:
                pdf.setStrokeColor(line)
                pdf.line(x, ry + 2.5 * mm, x + col_w, ry + 2.5 * mm)
            pdf.setFillColor(muted)
            pdf.setFont("Helvetica-Bold", 7.2)
            pdf.drawString(x, ry - 0.2 * mm, label)
            _draw_wrapped_pdf_text(pdf, value, x + 31 * mm, ry - 0.2 * mm, col_w - 31 * mm,
                                   size=8.2, color=navy, max_lines=2)

    draw_detail_column(left_rows, left + 6 * mm)
    draw_detail_column(right_rows, col2_x + 2 * mm)

    # --- Notes ---------------------------------------------------------------------
    notes_y = page_h - 180 * mm
    notes_h = 27 * mm
    pdf.setFillColor(light)
    pdf.setStrokeColor(border)
    pdf.roundRect(left, notes_y, content_w, notes_h, 4 * mm, fill=1, stroke=1)
    pdf.setFillColor(blue_dark)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(left + 6 * mm, notes_y + notes_h - 7 * mm, "Note")

    note_col_w = (content_w - 14 * mm) / 2
    pdf.setStrokeColor(line)
    pdf.line(left + content_w / 2, notes_y + 5 * mm, left + content_w / 2, notes_y + notes_h - 5 * mm)
    for x, label, value in [
        (left + 6 * mm, "Note consegna", status.note_operatore or "-"),
        (left + content_w / 2 + 6 * mm, "Note firma", status.signature_note or "-"),
    ]:
        pdf.setFillColor(navy)
        pdf.setFont("Helvetica-Bold", 7.6)
        pdf.drawString(x, notes_y + notes_h - 13 * mm, label)
        _draw_wrapped_pdf_text(pdf, value, x, notes_y + notes_h - 19 * mm, note_col_w,
                               size=7.2, color=navy, leading=8.5, max_lines=2)

    # --- Evidence: signature + delivery photo -------------------------------------
    evidence_y = 28 * mm
    evidence_h = notes_y - evidence_y - 5 * mm
    gap = 5 * mm
    panel_w = (content_w - gap) / 2

    def evidence_panel(x, title, raw, image_padding):
        pdf.setFillColor(white)
        pdf.setStrokeColor(border)
        pdf.roundRect(x, evidence_y, panel_w, evidence_h, 4 * mm, fill=1, stroke=1)
        title_h = 12 * mm
        pdf.setFillColor(blue_soft)
        pdf.roundRect(x, evidence_y + evidence_h - title_h, panel_w, title_h, 4 * mm, fill=1, stroke=0)
        pdf.setFillColor(blue_dark)
        pdf.setFont("Helvetica-Bold", 9.2)
        pdf.drawString(x + 5 * mm, evidence_y + evidence_h - 7.8 * mm, title)
        _draw_contained_image(
            pdf, raw,
            x + 4 * mm, evidence_y + 4 * mm,
            panel_w - 8 * mm, evidence_h - title_h - 7 * mm,
            padding=image_padding, background=True,
        )

    evidence_panel(left, "Firma cliente", signature, 5)
    evidence_panel(left + panel_w + gap, "Foto della consegna", photo, 4)

    # --- Footer --------------------------------------------------------------------
    footer_y = 15 * mm
    pdf.setStrokeColor(colors.HexColor("#CBD5E1"))
    pdf.line(left, footer_y + 6 * mm, right, footer_y + 6 * mm)
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 7.2)
    pdf.drawString(left, footer_y, "GiroFacile")
    footer_x = left + pdf.stringWidth("GiroFacile", "Helvetica-Bold", 7.2)
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 7.2)
    pdf.drawString(footer_x, footer_y, f" | POD {delivery.id} | Pagina 1 di 1")

    generated = local_now().replace(tzinfo=None)
    generated_label = f"Generato il {_pod_datetime(generated)}"
    pdf.drawRightString(right, footer_y, generated_label)

    pdf.setFillColor(colors.HexColor("#94A3B8"))
    pdf.setFont("Helvetica", 5.7)
    legal = "SHA-256: controllo di integrità dei file; non costituisce firma digitale qualificata o certificazione legale."
    pdf.drawCentredString(page_w / 2, footer_y - 4.5 * mm, legal)

    pdf.setTitle(f"GiroFacile - POD {delivery.id}")
    pdf.setAuthor("GiroFacile")
    pdf.setSubject("Prova di consegna")
    pdf.showPage()
    pdf.save()
    return stream.getvalue()


def save_delivery_evidence(db, route, delivery, status, payload, owner, action):
    signature = payload.get('signature_data')
    photo = payload.get('delivery_photo_data')
    if signature and not owner.delivery_signature_enabled:
        raise HTTPException(400, 'Firma cliente non attiva per questa azienda')
    signature_raw = normalize_image(signature, 'signature') if signature else None
    photo_raw = normalize_image(photo, 'delivery_photo') if photo else None
    if signature and not payload.get('signed_by_name', '').strip():
        raise HTTPException(400, 'Nome firmatario mancante')
    if owner.delivery_signature_enabled and not (signature_raw or (evidence_metadata(status)['has_signature'] and status.signed_by_name)):
        raise HTTPException(400, 'Firma cliente e nome firmatario richiesti prima di confermare la consegna')
    if action == 'complete' and owner.needs_photo_proof and not (photo_raw or status.delivery_photo_object_key):
        raise HTTPException(400, 'Foto della consegna obbligatoria')
    needs_storage = bool(signature_raw or photo_raw or (action == 'complete' and (
        object_storage.enabled() or owner.delivery_signature_enabled or owner.needs_photo_proof or status.signature_object_key or status.delivery_photo_object_key)))
    if not needs_storage:
        return
    storage = object_storage.get_storage()
    if signature_raw:
        store_evidence(db, storage, route, delivery, status, 'signature', signature_raw, 'image/png')
        status.signed_by_name = payload['signed_by_name'].strip()
        status.signature_note = (payload.get('signature_note') or '').strip() or None
        status.signed_at = local_now().replace(tzinfo=None)
    if photo_raw:
        store_evidence(db, storage, route, delivery, status, 'delivery_photo', photo_raw, 'image/jpeg')
    if action == 'complete':
        signature_raw = signature_raw or read_evidence(storage, route, delivery, status, 'signature')
        photo_raw = photo_raw or read_evidence(storage, route, delivery, status, 'delivery_photo')
        raw = generate_pod(route, delivery, status, owner, signature_raw, photo_raw)
        store_evidence(db, storage, route, delivery, status, 'pod', raw, 'application/pdf')
        status.pod_created_at = local_now().replace(tzinfo=None)


def evidence_response(db, route, delivery, kind):
    if kind not in ('signature', 'delivery_photo', 'pod') or delivery.route_plan_id != route.id:
        raise HTTPException(404, 'Documento non trovato')
    status = db.query(DeliveryStatus).filter_by(route_plan_id=route.id, delivery_id=delivery.id).first()
    if not status:
        raise HTTPException(404, 'Documento non trovato')
    key = getattr(status, kind + '_object_key')
    if not key:
        if kind == 'signature' and status.signature_data:
            return Response(normalize_image(status.signature_data, 'signature'), media_type='image/png',
                            headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
        raise HTTPException(404, 'Documento non trovato')
    object_storage.validate_key(key, route.user_id, route.id, delivery.id, kind)
    content_type = {'signature': 'image/png', 'delivery_photo': 'image/jpeg', 'pod': 'application/pdf'}[kind]
    from fastapi.responses import JSONResponse
    storage = object_storage.get_storage()
    return JSONResponse({'url': storage.signed_url(key, content_type, download=kind == 'pod'),
                         'expires_in': storage.seconds}, headers={'Cache-Control': 'no-store'})
