"""Conservative company-scoped matching; customer defaults never overwrite received data."""
import re
import unicodedata
from difflib import SequenceMatcher
from fastapi import HTTPException
from sqlalchemy import or_
from ..models import Customer
from ..order_models import CustomerSourceMapping


def normalize(value):
    value = unicodedata.normalize('NFKD', value or '').casefold()
    return ' '.join(re.sub(r'[^\w\s]', ' ', ''.join(c for c in value if not unicodedata.combining(c))).split())


def active(db, user_id):
    return db.query(Customer).filter_by(user_id=user_id, is_active=True, deleted_at=None)


def linked(db, order):
    return active(db, order.user_id).filter_by(id=order.customer_id).first() if order.customer_id else None


def candidate(customer, reason):
    return {'id':customer.id, 'name':customer.nome, 'address':customer.indirizzo, 'reason':reason}


def recognize(db, order):
    if order.customer_resolution == 'separate':
        return {'kind':'separate', 'candidates':[]}
    customer = linked(db, order)
    if customer:
        return {'kind':'linked', 'customer':candidate(customer, 'Associazione confermata' if order.customer_resolution=='confirmed' else 'Corrispondenza certa riconosciuta'), 'candidates':[]}
    if order.customer_id:
        return {'kind':'invalid', 'candidates':[]}
    if order.external_customer_id:
        mapping = db.query(CustomerSourceMapping).filter_by(user_id=order.user_id, source_id=order.source_id, external_customer_id=order.external_customer_id).first()
        if mapping:
            customer = active(db, order.user_id).filter_by(id=mapping.customer_id).first()
            if customer: return {'kind':'certain', 'candidates':[candidate(customer,'Codice cliente già associato alla fonte')]}
            return {'kind':'invalid', 'candidates':[]}
    name, address = normalize(order.recipient_name), normalize(order.delivery_address)
    exact, probable, exact_count = [], [], 0
    if name or address:
        for customer in active(db, order.user_id).order_by(Customer.id).yield_per(200):
            cn, ca = normalize(customer.nome), normalize(customer.indirizzo)
            if name and address and name == cn and address == ca:
                exact_count += 1
                if len(exact)<10: exact.append(candidate(customer,'Nome e indirizzo coincidono'))
            elif (name and name == cn) or (address and address == ca) or (name and address and SequenceMatcher(None,name,cn).ratio() >= .82 and SequenceMatcher(None,address,ca).ratio() >= .75):
                if len(probable) < 10: probable.append(candidate(customer,'Somiglianza da confermare: confronta nome e indirizzo'))
    if exact_count == 1: return {'kind':'certain','candidates':exact}
    return {'kind':'probable' if exact or probable else 'none','candidates':(exact+probable)[:10]}


def auto_link(db, order, actor):
    from .orders import record
    result = recognize(db, order)
    if result['kind'] == 'certain':
        order.customer_id = result['candidates'][0]['id']
        order.customer_resolution = 'automatic'
        record(db,order,actor,'customer_linked',{'customer_id':order.customer_id,'method':'certain'})
    return result


def effective(db, order):
    values = dict(order.operational_data)
    customer = linked(db, order)
    inherited = []
    if customer:
        defaults = {'recipient_name':customer.nome,'delivery_address':customer.indirizzo,
                    'tail_lift':customer.sponda,'pallet_truck':customer.transpallet,'ztl':customer.ztl,'notes':customer.note}
        for key,value in defaults.items():
            if values.get(key) is None or (key in ('recipient_name','delivery_address') and not values.get(key)):
                values[key] = value
                if value is not None: inherited.append(key)
        if values.get('time_from') is None and values.get('time_to') is None:
            for key in ('scarico_mattina_da','scarico_mattina_a','scarico_pomeriggio_da','scarico_pomeriggio_a'):
                value = getattr(customer,key)
                values[key] = value.isoformat() if value else None
            inherited.append('time_windows')
        values['tempo_scarico_min'] = customer.tempo_scarico_min
    return values, inherited


def anomalies(db, order, match=None):
    values, inherited = effective(db,order)
    result = []
    def add(code,message,blocking=False): result.append({'code':code,'message':message,'blocking':blocking})
    if not values.get('recipient_name'): add('recipient','Completa il destinatario.',True)
    if not values.get('delivery_address'): add('address','Completa l’indirizzo di consegna.',True)
    proof = order.address_verification or {}
    if proof.get('input_address') != values.get('delivery_address') or proof.get('stato_geocodifica') != 'verificato':
        add('verification','Verifica l’indirizzo effettivo di consegna.',True)
    match = match or recognize(db,order)
    if match['kind'] in ('probable','invalid'):
        add('customer','Conferma il cliente oppure scegli di mantenere separato il destinatario.',True)
    for field,label in [('weight_kg','peso'),('packages','colli')]:
        if values.get(field) is None: add(field,f'Indica {label}, se disponibili, per verificare il carico.')
    return result, values, inherited


def resolve(db, user, order, data, actor):
    from .orders import editable, touch, record
    editable(db,order,data.version)
    previous = order.customer_id
    if data.action == 'recognize':
        if order.customer_resolution == 'separate': order.customer_resolution = 'pending'
        auto_link(db,order,actor)
    elif data.action == 'separate':
        order.customer_id = None; order.customer_resolution = 'separate'
    else:
        if data.action == 'create':
            from .plans import check_customer_limit
            check_customer_limit(user,db)
            if not order.recipient_name or not order.delivery_address:
                raise HTTPException(422,'Completa nome e indirizzo prima di creare il cliente.')
            customer = Customer(user_id=user.id,nome=order.recipient_name,indirizzo=order.delivery_address)
            db.add(customer);db.flush()
        else:
            customer = active(db,user.id).filter_by(id=data.customer_id).first()
            if customer is None: raise HTTPException(404,'Cliente non disponibile in questa azienda.')
        if order.external_customer_id:
            mapping = db.query(CustomerSourceMapping).filter_by(user_id=user.id,source_id=order.source_id,external_customer_id=order.external_customer_id).first()
            if mapping and mapping.customer_id != customer.id:
                if active(db,user.id).filter_by(id=mapping.customer_id).first():
                    raise HTTPException(409,'Il codice esterno è già associato a un altro cliente. Mantieni separato questo ordine o verifica la fonte.')
                mapping.customer_id = customer.id
            if mapping is None:
                db.add(CustomerSourceMapping(user_id=user.id,source_id=order.source_id,external_customer_id=order.external_customer_id,customer_id=customer.id))
        order.customer_id = customer.id; order.customer_resolution = 'confirmed'
    order.status = 'da_verificare'; order.verification_status = 'pending'
    touch(order)
    record(db,order,actor,'customer_resolution',{'before':previous,'after':order.customer_id,'action':data.action})


def search(db,user_id,q):
    value = '%' + q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
    rows = active(db,user_id).filter(or_(Customer.nome.ilike(value,escape='\\'),Customer.indirizzo.ilike(value,escape='\\'))).order_by(Customer.nome,Customer.id).limit(20)
    return [candidate(c,'Risultato ricerca') for c in rows]
