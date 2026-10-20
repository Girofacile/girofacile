"""PDF della prova di consegna (POD): una sola pagina A4, layout "documento aziendale".

In alto logo e dati dell'azienda, numero del documento ed esito; poi destinatario e
data di consegna, i dettagli su due colonne e, affiancate, firma e foto. Testi lunghi
vengono accorciati e i riquadri delle immagini si adattano allo spazio rimasto, così
il documento non passa mai a una seconda pagina.
"""
import base64
import hashlib
import io
from html import escape
from pathlib import Path

from .route_enrichment import json_data

# Colori del sistema di stile (static/design-system/theme.css).
PRIMARY, TEXT, MUTED, BORDER, BG = '#1665ff', '#16213a', '#5a6680', '#dce1eb', '#edf0f6'
SUCCESS, SUCCESS_BG, INFO_BG = '#127a52', '#ddf3e8', '#e4f0ff'
GIROFACILE_LOGO = Path(__file__).resolve().parents[2] / 'static' / 'girofacile-logo.png'
LEGAL = ('Documento generato automaticamente da GiroFacile al momento della conferma della consegna. '
         'Gli hash SHA-256 garantiscono l’integrità dei file; non costituiscono firma digitale qualificata '
         'o certificazione legale.')


def _clip(value, limit):
    text = ' '.join(str(value or '').split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def _when(value):
    if not value:
        return '-'
    try:
        return value.strftime('%d/%m/%Y alle %H:%M')
    except AttributeError:
        return str(value)


def _number(value):
    text = f'{float(value or 0):.2f}'.rstrip('0').rstrip('.')
    return text.replace('.', ',')


def _count(n, one, many):
    n = int(n or 0)
    return f'{n} {one if n == 1 else many}'


def _company_logo(owner):
    """Logo caricato nel profilo azienda (data URL); None se assente o non leggibile."""
    from PIL import Image
    url = getattr(owner, 'company_logo_url', None) or ''
    if not url.startswith('data:image/') or ',' not in url:
        return None
    try:
        image = Image.open(io.BytesIO(base64.b64decode(url.split(',', 1)[1], validate=True)))
        image.thumbnail((240, 240))
        return image.convert('RGBA')
    except Exception:
        return None


def _girofacile_logo():
    # Stampato largo 5 mm: basta una versione piccola, il PDF resta leggero.
    from PIL import Image
    try:
        image = Image.open(GIROFACILE_LOGO)
        image.thumbnail((64, 64))
        return image.convert('RGBA')
    except Exception:
        return None


def _initials(name):
    return ''.join(word[0] for word in str(name or 'GF').split()[:2]).upper() or 'GF'


def generate_pod(route, delivery, status, owner, signature=None, photo=None):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph, Table, TableStyle

    W, H, M = 210 * mm, 297 * mm, 16 * mm
    C = {name: colors.HexColor(value) for name, value in dict(
        primary=PRIMARY, text=TEXT, muted=MUTED, border=BORDER, bg=BG,
        success=SUCCESS, success_bg=SUCCESS_BG, info_bg=INFO_BG).items()}

    def para(text, size=9, color='text', bold=False, leading=None, align=0):
        return Paragraph(text, ParagraphStyle('pod', fontName='Helvetica-Bold' if bold else 'Helvetica', fontSize=size,
                                              leading=leading or size * 1.3, textColor=C[color], alignment=align))

    def draw(text, x, y_top, width, **style):
        p = para(text, **style)
        _, height = p.wrap(width, H)
        p.drawOn(c, x, y_top - height)
        return height

    def table(rows, label_width, width):
        t = Table([[para(escape(k), size=8, color='muted'), para(escape(v), size=8.6, bold=strong)]
                   for k, v, strong in rows], colWidths=[label_width, width - label_width])
        t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 3.2),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 3.2), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                               ('RIGHTPADDING', (0, 0), (-1, -1), 4), ('LINEBELOW', (0, 0), (-1, -2), 0.5, C['border'])]))
        _, height = t.wrap(width, H)
        return t, height

    def picture(image, x, y, width, height, background='white', empty=''):
        c.setFillColor(colors.white if background == 'white' else C[background])
        c.setStrokeColor(C['border']); c.setLineWidth(0.8)
        c.roundRect(x, y, width, height, 2 * mm, stroke=1, fill=1)
        if image is None:
            c.setFillColor(C['muted']); c.setFont('Helvetica', 9)
            c.drawCentredString(x + width / 2, y + height / 2, empty)
            return
        pad = 2 * mm
        iw, ih = image.getSize()
        scale = min((width - 2 * pad) / iw, (height - 2 * pad) / ih)
        c.drawImage(image, x + (width - iw * scale) / 2, y + (height - ih * scale) / 2,
                    iw * scale, ih * scale, mask='auto')

    def load(raw):
        # La foto JPEG viene inserita così com'è (niente ricompressione): il PDF resta leggero.
        if not raw:
            return None
        try:
            return ImageReader(io.BytesIO(raw))
        except Exception:
            return None

    driver, vehicle = getattr(route, 'driver', None), getattr(route, 'vehicle', None)
    company = owner.company_name or owner.username
    number = f'POD-{route.id}-{delivery.id}'
    city = ' '.join(filter(None, [getattr(owner, 'company_zip', None), getattr(owner, 'company_city', None)]))
    company_lines = [f'P. IVA {owner.company_vat}' if getattr(owner, 'company_vat', None) else '',
                     ', '.join(filter(None, [getattr(owner, 'company_address', None), city])),
                     ' · '.join(filter(None, [getattr(owner, 'company_phone', None) and f'Tel. {owner.company_phone}',
                                              getattr(owner, 'company_email', None)]))]
    stops = len(getattr(route, 'deliveries', None) or [])
    orders = ', '.join(json_data(getattr(delivery, 'optimizer_details', None)).get('order_numbers') or [])
    unload = getattr(status, 'tempo_scarico_effettivo', None)
    signer = getattr(status, 'signed_by_name', None)

    stream = io.BytesIO()
    c = canvas.Canvas(stream, pagesize=(W, H))
    c.setTitle(f'Prova di consegna {number}')
    c.setAuthor(company)
    top = H - M

    # Intestazione: logo e dati dell'azienda, numero ed esito.
    logo = _company_logo(owner)
    if logo:
        iw, ih = logo.size
        scale = min(20 * mm / iw, 20 * mm / ih)
        c.drawImage(ImageReader(logo), M + (20 * mm - iw * scale) / 2, top - 20 * mm + (20 * mm - ih * scale) / 2,
                    iw * scale, ih * scale, mask='auto')
    else:
        c.setFillColor(C['info_bg']); c.roundRect(M, top - 20 * mm, 20 * mm, 20 * mm, 2 * mm, stroke=0, fill=1)
        c.setFillColor(C['primary']); c.setFont('Helvetica-Bold', 16)
        c.drawCentredString(M + 10 * mm, top - 12.5 * mm, _initials(company))
    draw(f'<b>{escape(_clip(company, 60))}</b>', M + 24 * mm, top - 1 * mm, 95 * mm, size=12)
    draw('<br/>'.join(escape(_clip(line, 90)) for line in company_lines if line), M + 24 * mm, top - 7.5 * mm,
         100 * mm, size=7.8, color='muted', leading=10)
    draw('PROVA DI CONSEGNA', W - M - 70 * mm, top - 1 * mm, 70 * mm, size=8, color='primary', bold=True, align=2)
    draw(f'<b>{number}</b>', W - M - 70 * mm, top - 6 * mm, 70 * mm, size=14, align=2)
    badge = 40 * mm
    c.setFillColor(C['success_bg']); c.roundRect(W - M - badge, top - 21 * mm, badge, 7 * mm, 3.5 * mm, stroke=0, fill=1)
    c.setFillColor(C['success']); c.setFont('Helvetica-Bold', 8.5)
    c.drawCentredString(W - M - badge / 2, top - 18.6 * mm, 'Consegna completata')
    c.setStrokeColor(C['border']); c.setLineWidth(0.6); c.line(M, top - 26 * mm, W - M, top - 26 * mm)

    # Destinatario e momento della consegna.
    y = top - 32 * mm
    col = (W - 2 * M - 8 * mm) / 2
    x2 = M + col + 8 * mm
    draw('DESTINATARIO', M, y, col, size=7.5, color='muted', bold=True)
    left = draw(f'<b>{escape(_clip(delivery.cliente_nome, 80))}</b><br/>{escape(_clip(delivery.indirizzo, 140))}',
                M, y - 5 * mm, col, size=10, leading=13)
    draw('CONSEGNATO IL', x2, y, col, size=7.5, color='muted', bold=True)
    right = draw(f'<b>{_when(status.completata_il)}</b>' + (f'<br/>Firmato da {escape(_clip(signer, 60))}' if signer else ''),
                 x2, y - 5 * mm, col, size=10, leading=13)
    y -= 5 * mm + max(left, right) + 7 * mm

    # Dettagli su due colonne.
    rows_left = [('Giro', _clip(' · '.join(filter(None, [route.nome, f'Giro {route.id}'])), 70), False)]
    if delivery.ordine:
        rows_left.append(('Fermata', f'{delivery.ordine} di {stops}' if stops else str(delivery.ordine), False))
    if orders:
        rows_left.append(('Ordine', _clip(orders, 70), False))
    rows_left.append(('Merce', f"{_count(delivery.colli, 'collo', 'colli')} · {_number(delivery.peso_kg)} kg", True))
    rows_right = [('Autista', _clip(' '.join(filter(None, [driver.nome, driver.cognome])), 60) if driver else '-', False),
                  ('Mezzo / targa', _clip(' · '.join(filter(None, [vehicle.nome, vehicle.targa])), 60) if vehicle else '-', False)]
    if unload:
        rows_right.append(('Tempo di scarico', f'{unload} min', False))
    rows_right.append(('Note consegna', _clip(status.note_operatore, 260) or '-', False))
    t1, h1 = table(rows_left, 26 * mm, col)
    t2, h2 = table(rows_right, 28 * mm, col)
    t1.drawOn(c, M, y - h1)
    t2.drawOn(c, x2, y - h2)
    y -= max(h1, h2) + 8 * mm

    # Firma e foto affiancate: il riquadro usa lo spazio rimasto sopra il piè di pagina.
    draw('FIRMA DEL CLIENTE', M, y, col, size=7.5, color='muted', bold=True)
    draw('FOTO DELLA CONSEGNA', x2, y, col, size=7.5, color='muted', bold=True)
    box = max(35 * mm, min(88 * mm, y - 5 * mm - 40 * mm))
    picture(load(signature), M, y - 5 * mm - box, col, box, empty='Firma non acquisita')
    picture(load(photo), x2, y - 5 * mm - box, col, box, background='bg', empty='Foto non acquisita')
    caption = [f'{escape(_clip(signer, 60))} · {_when(status.signed_at)}' if signer else '',
               f'Nota firma: {escape(_clip(status.signature_note, 160))}' if status.signature_note else '']
    if any(caption):
        draw('<br/>'.join(line for line in caption if line), M, y - 5 * mm - box - 3 * mm, col,
             size=8, color='muted', leading=10.5)

    # Piè di pagina: avviso, GiroFacile, numero, data di generazione e impronte dei file.
    c.setStrokeColor(C['border']); c.setLineWidth(0.6); c.line(M, 20 * mm, W - M, 20 * mm)
    draw(LEGAL, M, 18 * mm, W - 2 * M - 40 * mm, size=6.6, color='muted', leading=8.4)
    gf_logo = _girofacile_logo()
    if gf_logo:
        c.drawImage(ImageReader(gf_logo), W - M - 5 * mm, 12.2 * mm, 5 * mm, 5 * mm, mask='auto')
    draw('Generato con<br/><b>GiroFacile</b>', W - M - 38 * mm, 18 * mm, 31 * mm, size=6.6, color='muted', leading=8.4, align=2)
    from ..core.utils import local_now
    hashes = ' · '.join(f'{label} {hashlib.sha256(raw).hexdigest()[:16]}'
                        for label, raw in (('firma', signature), ('foto', photo)) if raw)
    c.setFont('Helvetica', 7); c.setFillColor(C['muted'])
    c.drawString(M, 8 * mm, f"{number} · generato il {local_now().strftime('%d/%m/%Y %H:%M')}"
                 + (f' · SHA-256 {hashes}' if hashes else ''))
    c.drawRightString(W - M, 8 * mm, 'Pagina 1 di 1')
    c.showPage()
    c.save()
    return stream.getvalue()
