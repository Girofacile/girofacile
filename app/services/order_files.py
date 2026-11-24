"""Bounded CSV/XLSX reader. Uses the existing openpyxl dependency, no customer import changes."""
import csv
import hashlib
import re
import io
import json
import zipfile
from datetime import date,datetime,time
from fastapi import HTTPException
from openpyxl import load_workbook
from ..schemas.order_sources import MAX_BYTES,MAX_ROWS,ExternalOrder
from .order_grouping import normalize

FIELDS=list(ExternalOrder.model_fields)
# Nomi abbreviati tipici dei gestionali AS400 (es. NUMORD, RAGSOC, DTCONS, LOCALI) compresi.
ALIASES={'external_id':['idordine','id','nordine','numeroordine','numord','nrord','nrordine'], 'number':['numeroordine','nordine','numero','numord','nrord','nrordine'],
 'external_customer_id':['codcli','codicecliente'], 'recipient_name':['ragionesociale','cliente','destinatario','ragsoc','ragsociale','destin','nominativo'],
 'phone':['telefono','tel','cellulare','recapito','telefonodestinatario'],
 'delivery_address':['indsped','indirizzo','indirizzoconsegna','indir'], 'requested_date':['datacons','dataconsegna','dtcons','dtconsegna'],
 'weight_kg':['peso','pesokg'],'packages':['ncolli','colli','nrcolli'],'tail_lift':['pedana','sponda'],
 'pallet_truck':['transpallet'],'ztl':['ztl'],'notes':['note'],'time_from':['dalle'],'time_to':['alle'],
 'pallets':['pallet'],'volume_m3':['volume'],'requirements':['requisiti'],
 # Indirizzo a campi separati: via, civico, CAP, comune, provincia.
 'street':['via','strada'],'street_number':['civico','numerocivico','ncivico','numero civico'],
 'postal_code':['cap'],'city':['comune','citta','città','localita','località','locali'],'province':['provincia','prov']}


def requested_date(value):
    """Data consegna dai formati più comuni, compresi quelli dei gestionali AS400.

    GG/MM/AAAA, GG/MM/AA, GG-MM-AAAA, GG.MM.AAAA, AAAA-MM-GG, AAAAMMGG e GGMMAAAA.
    Le 6 cifre senza separatori (GGMMAA o AAMMGG) sono ambigue e restano un errore."""
    text=value.strip()
    if 'T' in text: return datetime.fromisoformat(text).date().isoformat()
    if text.isdigit() and len(text)==8:
        return datetime.strptime(text,'%Y%m%d' if int(text[:4])>=1900 else '%d%m%Y').date().isoformat()
    if len(text)>=5 and text[:4].isdigit() and text[4]=='-':
        return datetime.strptime(text,'%Y-%m-%d').date().isoformat()
    for separator in '/-.':
        if separator in text:
            year='%Y' if len(text.rsplit(separator,1)[-1])==4 else '%y'
            return datetime.strptime(text,f'%d{separator}%m{separator}{year}').date().isoformat()
    raise ValueError(text)


# Riconoscimento per parole, dopo quello esatto: intestazioni scritte «a mano» come «N° Ord.»,
# «Rag. Sociale Cliente», «Tel. cliente», «Orario da». Le regole si provano in quest'ordine;
# ogni intestazione va a un solo dato e ogni dato a una sola intestazione.
def _has(*words): return lambda t: any(w in t for w in words)
def _all(*groups): return lambda t: all(any(w in t for w in g) for g in groups)
KEYWORD_RULES=[
    ('external_customer_id', _all({'cod','codice','id'},{'cli','cliente','clienti'})),
    ('phone', _has('tel','telefono','cell','cellulare','telefonico','recapito','phone')),
    ('requested_date', lambda t: _has('data','dt','giorno')(t) and not _has('ordine','ord')(t) or _has('consegna','evasione')(t) and _has('data','dt','giorno')(t)),
    ('number', lambda t: _has('ord','ordine','ordini','order','doc','documento')(t) and not _has('data','dt','cliente','cod')(t)),
    ('recipient_name', lambda t: _has('rag','ragione','sociale','destinatario','destin','denominazione','nominativo','intestatario','cliente','nome','insegna')(t) and not _has('cod','codice','tel','telefono','indirizzo')(t)),
    ('street_number', _has('civico','civ')),
    ('delivery_address', _has('indirizzo','ind','indir','address','recapito consegna')),
    ('postal_code', _has('cap','postale')),
    ('city', _has('citta','comune','localita','loc','paese','city')),
    ('province', _has('prov','provincia','pr')),
    ('packages', _has('colli','collo','pacchi','cartoni')),
    ('weight_kg', _has('peso','kg','chili')),
    ('pallet_truck', _has('transpallet')),
    ('pallets', _has('pallet','pallets','bancali','bancale','pedane')),
    ('time_from', lambda t: _has('dalle','apertura')(t) or _has('orario','ora','fascia')(t) and _has('da','inizio','min')(t)),
    ('time_to', lambda t: _has('alle','chiusura')(t) or _has('orario','ora','fascia')(t) and _has('a','fine','max')(t)),
    ('time_from', _has('finestra','fascia')),
    ('tail_lift', _has('sponda')),
    ('ztl', _has('ztl')),
    ('volume_m3', _has('volume','m3','mc')),
    ('requirements', _has('requisiti','esigenze')),
    ('notes', _has('note','nota','annotazioni','commenti','istruzioni','osservazioni')),
]


def suggestions(headers):
    def key(value): return normalize(value).replace(' ','').replace('_','')
    result={}
    for target in FIELDS:
        candidates=[h for h in headers if key(h) in {key(target),*(key(a) for a in ALIASES.get(target,[]))}]
        if len(candidates)==1: result[target]=candidates[0]
    used=set(result.values())
    # Una colonna «Finestra/Fascia di consegna» vale più degli orari di apertura del negozio.
    if 'time_from' not in result and 'time_to' not in result:
        for header in headers:
            tokens=set(normalize(header).replace('_',' ').split())
            if header not in used and tokens&{'finestra','fascia'} and not tokens&{'dalle','alle','da','a'}:
                result['time_from']=header;used.add(header);break
    for header in headers:
        if header in used: continue
        tokens=set(normalize(header).replace('_',' ').split())
        for target,rule in KEYWORD_RULES:
            if target not in result and rule(tokens):
                result[target]=header;used.add(header);break
    if 'external_id' not in result and 'number' in result: result['external_id']=result['number']
    # CAP e comune in colonne proprie: la colonna «Indirizzo» contiene solo via e civico (tipico dell'AS400).
    if {'postal_code','city'}<=result.keys() and 'delivery_address' in result and 'street' not in result:
        result['street']=result.pop('delivery_address')
    return result


def validate_rows(headers, rows):
    from openpyxl.utils import get_column_letter
    if not headers: raise HTTPException(422,'La prima riga deve contenere le intestazioni delle colonne.')
    if len(headers)>50: raise HTTPException(422,'Il file ha più di 50 colonne: tieni solo quelle utili agli ordini.')
    for i,h in enumerate(headers):
        if not h: raise HTTPException(422,f'La colonna {get_column_letter(i+1)} ha dati ma nessuna intestazione: scrivi il suo nome nella prima riga.')
        if len(h)>160: raise HTTPException(422,f'L\'intestazione della colonna {get_column_letter(i+1)} è troppo lunga (massimo 160 caratteri).')
    doubles=sorted({h for h in headers if headers.count(h)>1})
    if doubles: raise HTTPException(422,'Ci sono intestazioni ripetute: '+', '.join('«'+h+'»' for h in doubles)+'. Rinominale in modo che siano tutte diverse.')
    if not rows or len(rows)>MAX_ROWS: raise HTTPException(422,f'Il file deve contenere da 1 a {MAX_ROWS} ordini. Suddividi i file più grandi.')
    for row in rows:
        if len(row)>50 or any(len(str(v))>5000 for v in row.values()): raise HTTPException(422,'Troppi campi o una cella supera 5000 caratteri.')
    return headers,rows


class ChooseSheet(HTTPException):
    """Il file Excel ha più fogli: l'utente sceglie quale importare."""
    def __init__(self, sheets):
        super().__init__(422, {'code': 'choose_sheet', 'sheets': sheets,
                               'message': f'Il file ha {len(sheets)} fogli: scegli quale contiene gli ordini.'})


def _cell_name(cell):
    from openpyxl.utils import get_column_letter
    return f'{get_column_letter(cell.column)}{cell.row}'


def _drop_empty_columns(headers, rows):
    """Colonne senza intestazione e senza dati (tipiche dei file formattati) vengono ignorate."""
    keep = [i for i, h in enumerate(headers) if h or any(i < len(r) and r[i] not in (None, '') for r in rows)]
    return [headers[i] for i in keep], [[r[i] if i < len(r) else None for i in keep] for r in rows]


def read_file(content,filename,sheet=None):
    """Legge CSV o XLSX. Ogni problema ha il suo messaggio, per correggere il file senza tentativi."""
    if len(content)>MAX_BYTES: raise HTTPException(413,'Il file supera il limite di 2 MB: dividilo in file più piccoli.')
    name=filename.lower()
    if name.endswith('.xls'): raise HTTPException(422,'Il formato .xls (Excel vecchio) non è supportato: in Excel usa «Salva con nome» → «Cartella di lavoro di Excel (.xlsx)».')
    if not name.endswith(('.csv','.xlsx')): raise HTTPException(422,'Usa un file Excel (.xlsx) o CSV.')
    too_many=f'Il file ha più di {MAX_ROWS} ordini: dividilo in più file.'
    if name.endswith('.csv'):
        try: text=content.decode('utf-8-sig')
        except UnicodeDecodeError: text=content.decode('cp1252',errors='replace')
        try: dialect=csv.Sniffer().sniff(text[:8192],delimiters=',;\t')
        except csv.Error:
            # Righe con un numero di colonne diverso confondono il riconoscimento: vale il separatore più usato nell'intestazione.
            first=text.split(chr(10),1)[0]
            class dialect(csv.excel): delimiter=max((';',',',chr(9)),key=first.count)
        reader=csv.reader(io.StringIO(text),dialect)
        try: headers=[h.strip() for h in next(reader)]
        except StopIteration: raise HTTPException(422,'Il file è vuoto.') from None
        data=[]
        for line,values in enumerate(reader,start=2):
            if not any(v.strip() for v in values): continue
            if len(values)!=len(headers):
                raise HTTPException(422,f'La riga {line} ha {len(values)} colonne invece di {len(headers)}: controlla separatori (; o ,) e virgolette.')
            data.append(values)
            if len(data)>MAX_ROWS: raise HTTPException(422,too_many)
    else:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                files=archive.infolist()
                if len(files)>1000 or sum(f.file_size for f in files)>20*1024*1024 or any('externallinks/' in f.filename.lower() or 'vbaproject' in f.filename.lower() for f in files):
                    raise HTTPException(422,'Il file Excel contiene macro o collegamenti ad altri file, oppure è troppo grande una volta aperto: salvalo come semplice .xlsx senza collegamenti.')
            book=load_workbook(io.BytesIO(content),read_only=True,data_only=False,keep_links=False)
        except HTTPException: raise
        except Exception:
            raise HTTPException(422,'Il file non è un Excel valido (.xlsx): aprilo in Excel e salvalo di nuovo come .xlsx.') from None
        try:
            sheets=book.worksheets
            if sheet is not None:
                chosen=[ws for ws in sheets if ws.title==sheet]
                if not chosen: raise HTTPException(422,f'Il foglio «{sheet}» non c\'è nel file: caricalo di nuovo.')
                ws=chosen[0]
            elif len(sheets)>1:
                def count(w):
                    filled=0
                    for values in w.iter_rows(values_only=True):
                        if any(v not in (None,'') for v in values): filled+=1
                        if filled>MAX_ROWS+1: break
                    return max(0,filled-1)
                raise ChooseSheet([{'name':w.title,'rows':count(w)} for w in sheets])
            else:
                ws=sheets[0]
            if (ws.max_column or 0)>50: raise HTTPException(422,'Il foglio ha più di 50 colonne: tieni solo quelle utili agli ordini.')
            data=[]
            for cells in ws.iter_rows():
                values=[]
                for cell in cells:
                    if cell.data_type=='f':
                        raise HTTPException(422,f'La cella {_cell_name(cell)} contiene una formula: in Excel seleziona tutto, copia e usa «Incolla valori», poi salva.')
                    if cell.data_type=='e':
                        raise HTTPException(422,f'La cella {_cell_name(cell)} contiene un errore di Excel (#N/D, #VALORE!…): correggila e salva di nuovo.')
                    value=cell.value
                    values.append(value.isoformat() if isinstance(value,(datetime,date,time)) else value)
                if any(v is not None and v!='' for v in values): data.append(values)
                if len(data)>MAX_ROWS+1: raise HTTPException(422,too_many)
        finally: book.close()
        if not data: raise HTTPException(422,'Il foglio è vuoto.')
        headers=[str(v if v is not None else '').strip() for v in data[0]]
        data=data[1:]
    headers,data=_drop_empty_columns(headers,data)
    if not data: raise HTTPException(422,'Il file ha solo la riga delle intestazioni: aggiungi gli ordini sotto.')
    rows=[dict(zip(headers,r)) for r in data]
    return validate_rows(headers,rows)


def mapped(row,mapping):
    data={key:row.get(column) for key,column in mapping.items() if key in FIELDS}
    for key,value in list(data.items()):
        if isinstance(value,str): value=value.strip()
        if value=='': value=None
        if key in ('external_id','number','external_customer_id') and type(value) in (int,float):
            if not float(value).is_integer() or abs(value)>=10**15: raise ValueError('Usa codici in formato testo.')
            value=str(int(value))
        if value is not None and key in ('tail_lift','pallet_truck','ztl') and isinstance(value,str):
            true={'true','si','sì','yes','1'};false={'false','no','0'}
            if value.casefold() not in true|false: raise ValueError(f'{key}: usa Sì/No o True/False.')
            value=value.casefold() in true
        if value is not None and key in ('weight_kg','pallets','volume_m3','packages') and isinstance(value,str):
            value=value.replace(',','.')
        # Da Excel una data AS400 come 20261113 può arrivare come numero.
        if key=='requested_date' and type(value) in (int,float) and float(value).is_integer(): value=str(int(value))
        if value is not None and key=='requested_date' and isinstance(value,str):
            try: value=requested_date(value)
            except ValueError:
                raise ValueError(f'Data consegna «{value}» non valida: usa GG/MM/AAAA (es. 12/11/2026) oppure AAAAMMGG (es. 20261112).') from None
        if value is not None and key=='items' and isinstance(value,str): value=json.loads(value)
        data[key]=value
    # Fascia oraria scritta in una sola colonna («09:00-12:00»): si divide in «dalle» e «alle».
    window=data.get('time_from')
    if isinstance(window,str) and not data.get('time_to'):
        match=re.fullmatch(r'\s*(\d{1,2})[:.](\d{2})\s*(?:-|–|—|/|alle|a)\s*(\d{1,2})[:.](\d{2})\s*',window)
        if match:
            h1,m1,h2,m2=match.groups()
            data['time_from'],data['time_to']=f'{int(h1):02d}:{m1}',f'{int(h2):02d}:{m2}'
    # Senza numero ordine nel file: codice stabile ricavato dai dati della riga. Ricaricando lo stesso
    # file gli ordini identici vengono riconosciuti; se una riga cambia, diventa un ordine nuovo.
    if 'number' not in mapping and not data.get('external_id'):
        basis='|'.join(f'{k}={data[k]}' for k in sorted(data) if k not in ('number','external_id','items') and data[k] is not None)
        code='AUTO-'+hashlib.sha1(basis.encode('utf-8')).hexdigest()[:8].upper()
        data['number']=data['external_id']=code
    elif 'number' not in mapping and not data.get('number'): data['number']=data['external_id']
    if data.get('items') is None: data['items']=[]
    return ExternalOrder.model_validate(data).model_dump(mode='json')
