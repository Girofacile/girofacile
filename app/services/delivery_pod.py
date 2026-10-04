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
        return value.strftime("%d/%m/%Y - %H:%M")
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
        while last and stringWidth(last + "...", font, size) > width:
            last = last[:-1]
        lines[-1] = (last.rstrip() + "...") if last else "..."

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
    """Generate a monochrome, print-friendly, single-page A4 proof of delivery."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4, pageCompression=1)
    page_w, page_h = A4

    black = colors.HexColor("#111111")
    dark_grey = colors.HexColor("#4A4A4A")
    mid_grey = colors.HexColor("#777777")
    light_grey = colors.HexColor("#C9C9C9")
    very_light = colors.HexColor("#E6E6E6")

    left = 16 * mm
    right = page_w - 16 * mm
    content_w = right - left

    def hline(y, x1=left, x2=right, width=0.45, dashed=False, color=light_grey):
        pdf.setStrokeColor(color)
        pdf.setLineWidth(width)
        pdf.setDash(2, 2) if dashed else pdf.setDash()
        pdf.line(x1, y, x2, y)
        pdf.setDash()

    def section_title(text, y):
        pdf.setFillColor(black)
        pdf.setFont("Helvetica-Bold", 8.6)
        pdf.drawString(left, y, text.upper())
        hline(y - 2.5 * mm, width=0.55, color=black)

    def field(label, value, x, y, width, label_width=27 * mm, max_lines=2):
        pdf.setFillColor(dark_grey)
        pdf.setFont("Helvetica-Bold", 7.1)
        pdf.drawString(x, y, str(label))
        _draw_wrapped_pdf_text(
            pdf, value, x + label_width, y,
            width - label_width,
            font="Helvetica", size=8.2, color=black,
            leading=9.3, max_lines=max_lines,
        )

    company_name = getattr(owner, "company_name", None) or owner.username or "Azienda"
    company_address = _pod_company_address(owner)
    company_vat = (getattr(owner, "company_vat", None) or "").strip()
    company_cf = (getattr(owner, "company_fiscal_code", None) or "").strip()
    company_phone = (getattr(owner, "company_phone", None) or "").strip()
    company_email = (getattr(owner, "company_email", None) or getattr(owner, "email", None) or "").strip()
    company_pec = (getattr(owner, "company_pec", None) or "").strip()

    # ------------------------------------------------------------------
    # Letterhead: company identity first, GiroFacile remains in footer.
    # ------------------------------------------------------------------
    top = page_h - 16 * mm
    logo_raw = _pod_logo_bytes(getattr(owner, "company_logo_url", None))
    logo_w = 30 * mm
    logo_h = 18 * mm

    if logo_raw:
        _draw_contained_image(pdf, logo_raw, left, top - logo_h, logo_w, logo_h, padding=0, background=False)
        company_x = left + logo_w + 5 * mm
    else:
        company_x = left

    company_text_w = 85 * mm - (company_x - left)
    _draw_wrapped_pdf_text(
        pdf, company_name, company_x, top - 2 * mm, company_text_w,
        font="Helvetica-Bold", size=12.5, color=black, max_lines=1,
    )
    company_y = top - 8 * mm
    if company_address:
        company_y = _draw_wrapped_pdf_text(
            pdf, company_address, company_x, company_y, company_text_w,
            size=7.4, color=dark_grey, leading=8.6, max_lines=2,
        )

    fiscal_bits = []
    if company_vat:
        fiscal_bits.append(f"P. IVA {company_vat}")
    if company_cf:
        fiscal_bits.append(f"C.F. {company_cf}")
    if fiscal_bits:
        company_y = _draw_wrapped_pdf_text(
            pdf, " - ".join(fiscal_bits), company_x, company_y - 0.5 * mm,
            company_text_w, size=7.2, color=dark_grey, max_lines=1,
        )

    contact_bits = [v for v in (company_phone, company_email) if v]
    if contact_bits:
        company_y = _draw_wrapped_pdf_text(
            pdf, " - ".join(contact_bits), company_x, company_y - 0.5 * mm,
            company_text_w, size=7.2, color=dark_grey, max_lines=1,
        )
    if company_pec:
        _draw_wrapped_pdf_text(
            pdf, f"PEC {company_pec}", company_x, company_y - 0.5 * mm,
            company_text_w, size=7.2, color=dark_grey, max_lines=1,
        )

    title_x = page_w - 82 * mm
    pdf.setFillColor(black)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawRightString(right, top - 1 * mm, "PROVA DI CONSEGNA")
    pdf.setFillColor(dark_grey)
    pdf.setFont("Helvetica", 8.2)
    pdf.drawRightString(right, top - 7 * mm, f"POD N. {delivery.id}")
    pdf.drawRightString(right, top - 12 * mm, "Documento di avvenuta consegna")

    header_rule_y = top - 24 * mm
    hline(header_rule_y, width=0.8, color=black)

    # ------------------------------------------------------------------
    # Status + document metadata: no colored banner.
    # ------------------------------------------------------------------
    status_y = header_rule_y - 7 * mm
    pdf.setFillColor(black)
    pdf.setFont("Helvetica-Bold", 9.2)
    pdf.drawString(left, status_y, "STATO: CONSEGNA COMPLETATA")
    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(dark_grey)
    pdf.drawRightString(right, status_y, f"Data consegna: {_pod_datetime(status.completata_il)}")
    hline(status_y - 4 * mm, width=0.35, dashed=True, color=mid_grey)

    # ------------------------------------------------------------------
    # Delivery details: classic two-column document layout.
    # ------------------------------------------------------------------
    details_title_y = status_y - 11 * mm
    section_title("Dati consegna", details_title_y)

    driver = route.driver
    vehicle = route.vehicle
    driver_name = " ".join(filter(None, [getattr(driver, "nome", None), getattr(driver, "cognome", None)])) if driver else "-"
    vehicle_name = (getattr(vehicle, "nome", None) or "").strip() if vehicle else ""
    if vehicle and getattr(vehicle, "targa", None):
        vehicle_name = (vehicle_name + " / " + vehicle.targa).strip(" /")
    vehicle_name = vehicle_name or "-"

    col_gap = 9 * mm
    col_w = (content_w - col_gap) / 2
    right_col_x = left + col_w + col_gap
    data_top = details_title_y - 9 * mm
    row_h = 10 * mm

    left_rows = [
        ("Cliente", delivery.cliente_nome or "-"),
        ("Indirizzo", delivery.indirizzo or "-"),
        ("Giro", f'{route.id} - {route.nome or "Giro consegne"}'),
        ("Consegna", str(delivery.id)),
        ("Data / ora", _pod_datetime(status.completata_il)),
    ]
    right_rows = [
        ("Autista", driver_name),
        ("Mezzo / targa", vehicle_name),
        ("Colli / peso", f'{delivery.colli or 0} / {delivery.peso_kg or 0} kg'),
        ("Firmatario", status.signed_by_name or "-"),
        ("Data firma", _pod_datetime(status.signed_at)),
    ]

    for idx, (label, value) in enumerate(left_rows):
        y = data_top - idx * row_h
        field(label, value, left, y, col_w, label_width=24 * mm, max_lines=2)
        if idx < len(left_rows) - 1:
            hline(y - 4.1 * mm, x1=left, x2=left + col_w, width=0.25, color=very_light)

    for idx, (label, value) in enumerate(right_rows):
        y = data_top - idx * row_h
        field(label, value, right_col_x, y, col_w, label_width=27 * mm, max_lines=2)
        if idx < len(right_rows) - 1:
            hline(y - 4.1 * mm, x1=right_col_x, x2=right_col_x + col_w, width=0.25, color=very_light)

    # Thin vertical separator only; no boxes.
    pdf.setStrokeColor(very_light)
    pdf.setLineWidth(0.35)
    pdf.line(left + col_w + col_gap / 2, data_top + 2 * mm,
             left + col_w + col_gap / 2, data_top - 4 * row_h - 5 * mm)

    details_bottom = data_top - 5 * row_h + 2 * mm
    hline(details_bottom, width=0.55, color=black)

    # ------------------------------------------------------------------
    # Notes: one clean section, no panel fills.
    # ------------------------------------------------------------------
    notes_title_y = details_bottom - 8 * mm
    section_title("Note", notes_title_y)

    notes_y = notes_title_y - 9 * mm
    half = (content_w - 8 * mm) / 2
    pdf.setFillColor(dark_grey)
    pdf.setFont("Helvetica-Bold", 7.2)
    pdf.drawString(left, notes_y, "Note consegna")
    _draw_wrapped_pdf_text(
        pdf, status.note_operatore or "-", left, notes_y - 5 * mm, half,
        size=7.5, color=black, leading=8.6, max_lines=2,
    )
    pdf.drawString(left + half + 8 * mm, notes_y, "Note firma")
    _draw_wrapped_pdf_text(
        pdf, status.signature_note or "-", left + half + 8 * mm, notes_y - 5 * mm, half,
        size=7.5, color=black, leading=8.6, max_lines=2,
    )

    notes_bottom = notes_y - 14 * mm
    hline(notes_bottom, width=0.35, dashed=True, color=mid_grey)

    # ------------------------------------------------------------------
    # Evidence: simple black labels and thin dashed frames.
    # Keep the original photo colors because it is evidence.
    # ------------------------------------------------------------------
    evidence_title_y = notes_bottom - 8 * mm
    section_title("Prova di consegna", evidence_title_y)

    evidence_top = evidence_title_y - 7 * mm
    footer_rule_y = 21 * mm
    evidence_bottom = footer_rule_y + 9 * mm
    evidence_h = evidence_top - evidence_bottom
    panel_gap = 7 * mm
    panel_w = (content_w - panel_gap) / 2
    image_top_pad = 8 * mm

    def evidence_area(x, title, raw, padding):
        pdf.setFillColor(black)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(x, evidence_top, title)
        box_y = evidence_bottom
        box_h = evidence_h - image_top_pad
        pdf.setStrokeColor(mid_grey)
        pdf.setLineWidth(0.45)
        pdf.setDash(3, 2)
        pdf.rect(x, box_y, panel_w, box_h, fill=0, stroke=1)
        pdf.setDash()
        _draw_contained_image(
            pdf, raw,
            x + 2.5 * mm, box_y + 2.5 * mm,
            panel_w - 5 * mm, box_h - 5 * mm,
            padding=padding, background=False,
        )

    evidence_area(left, "Firma cliente", signature, 4)
    evidence_area(left + panel_w + panel_gap, "Foto della consegna", photo, 3)

    # ------------------------------------------------------------------
    # Footer: print-friendly and discreet.
    # ------------------------------------------------------------------
    hline(footer_rule_y, width=0.55, color=black)

    footer_y = 14 * mm
    pdf.setFillColor(black)
    pdf.setFont("Helvetica-Bold", 6.8)
    pdf.drawString(left, footer_y, "GiroFacile")
    footer_x = left + pdf.stringWidth("GiroFacile", "Helvetica-Bold", 6.8)
    pdf.setFont("Helvetica", 6.8)
    pdf.setFillColor(dark_grey)
    pdf.drawString(footer_x, footer_y, f" | POD {delivery.id} | Pagina 1 di 1")
    generated = local_now().replace(tzinfo=None)
    pdf.drawRightString(right, footer_y, f"Generato il {_pod_datetime(generated)}")

    pdf.setFillColor(mid_grey)
    pdf.setFont("Helvetica", 5.4)
    legal = "SHA-256: controllo di integrita dei file; non costituisce firma digitale qualificata o certificazione legale."
    pdf.drawCentredString(page_w / 2, 9.5 * mm, legal)

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
