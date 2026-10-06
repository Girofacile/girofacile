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


def generate_pod(route, delivery, status, owner, signature=None, photo=None):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether, Image as PDFImage
    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    styles['BodyText'].spaceBefore = 0
    styles['BodyText'].spaceAfter = 0
    story = [Paragraph('GiroFacile - Prova di consegna', styles['Title']),
             Paragraph('Consegna completata', styles['Heading2'])]
    driver = route.driver
    vehicle = route.vehicle
    rows = [('Azienda', owner.company_name or owner.username),
            ('Giro', f'{route.id} - {route.nome or ""}'), ('Consegna', delivery.id),
            ('Cliente', delivery.cliente_nome), ('Indirizzo', delivery.indirizzo),
            ('Data e ora (Europe/Rome)', status.completata_il),
            ('Autista', ' '.join(filter(None, [driver.nome, driver.cognome])) if driver else '-'),
            ('Mezzo / targa', f'{vehicle.nome or ""} / {vehicle.targa or ""}' if vehicle else '-'),
            ('Colli / peso kg', f'{delivery.colli or 0} / {delivery.peso_kg or 0}'),
            ('Firmatario', status.signed_by_name or '-'), ('Data firma', status.signed_at or '-'),
            ('Note consegna', status.note_operatore or '-'), ('Note firma', status.signature_note or '-')]
    for label, value in rows:
        text = escape(str(value or '-')).replace('\n', '<br/>')
        story.append(Paragraph(f'<b>{label}:</b> {text}', styles['BodyText']))
        story.append(Spacer(1, 2 * mm))
    for label, raw, width, height in [('Firma cliente', signature, 130*mm, 45*mm),
                                     ('Foto della consegna', photo, 160*mm, 75*mm)]:
        group = [Paragraph(label + ('' if raw else ': non acquisita'), styles['Heading3'])]
        if raw:
            image = PDFImage(io.BytesIO(raw))
            scale = min(width / image.imageWidth, height / image.imageHeight)
            image.drawWidth = image.imageWidth * scale
            image.drawHeight = image.imageHeight * scale
            image.hAlign = 'LEFT'
            group.append(image)
        story.append(KeepTogether(group))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph('Gli hash SHA-256 sono controlli di integrità dei file; non costituiscono firma digitale qualificata o certificazione legale.', styles['BodyText']))
    def footer(canvas, doc):
        canvas.setFillColor(colors.grey)
        canvas.setFont('Helvetica', 9)
        canvas.drawString(20*mm, 12*mm, f'GiroFacile | POD {delivery.id} | Pagina {doc.page}')
    SimpleDocTemplate(stream, pagesize=(210*mm, 297*mm), leftMargin=20*mm, rightMargin=20*mm,
                      topMargin=18*mm, bottomMargin=22*mm).build(story, onFirstPage=footer, onLaterPages=footer)
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
        object_storage.configured() or owner.delivery_signature_enabled or owner.needs_photo_proof or status.signature_object_key or status.delivery_photo_object_key)))
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
