"""Dati demo per le riprese: un'azienda di distribuzione a Bologna (dati d'esempio)."""
import datetime as dt, sys, os
sys.path.insert(0, os.environ.get("GIROFACILE_REPO", "."))
from app.database import SessionLocal
from app.models import User, Deposit, Vehicle, Driver, Customer

db = SessionLocal()
u = db.query(User).filter_by(username="azienda_demo").one()
u.company_name = "Distribuzioni Emilia"
u.onboarding_completed = True
u.onboarding_dismissed = True
u.tutor_state = "completato"
u.tutor_completed_at = dt.datetime.utcnow()
uid = u.id
for M in (Customer, Vehicle, Driver, Deposit):
    db.query(M).filter_by(user_id=uid).delete()

db.add(Deposit(user_id=uid, nome="Magazzino Bologna", indirizzo="Via dell'Industria 20, 40138 Bologna BO",
               predefinito=True, lat=44.5050, lon=11.3920))
for n, t, m in [("Furgone 1", "GF 101 BO", "Fiat Ducato"), ("Furgone 2", "GF 202 BO", "Iveco Daily"),
                ("Furgone 3", "GF 303 BO", "Ford Transit")]:
    db.add(Vehicle(user_id=uid, nome=n, targa=t, marca=m.split()[0], modello=m.split()[1],
                   consumo_l_100km=9.5, consumo_primario_100km=9.5, capacita_kg=1400, capacita_colli=120, ha_sponda=True))
for n, c in [("Marco", "Bianchi"), ("Luca", "Ferri"), ("Sara", "Conti")]:
    db.add(Driver(user_id=uid, nome=n, cognome=c, patente="C"))

C = [  # nome, via, cap, lat, lon, finestra mattina
    ("Bar Centrale", "Via dell'Indipendenza 12", "40121", 44.4985, 11.3440, ("07:00", "10:00")),
    ("Pizzeria Da Gino", "Via del Pratello 41", "40122", 44.4940, 11.3310, ("10:00", "12:00")),
    ("Alimentari Rossi", "Via Saragozza 88", "40123", 44.4890, 11.3260, ("08:00", "12:00")),
    ("Hotel Bellavista", "Via Marco Polo 51", "40131", 44.5180, 11.3170, ("07:30", "11:00")),
    ("Trattoria Il Ponte", "Via Andrea Costa 104", "40134", 44.4920, 11.3080, ("09:00", "11:30")),
    ("Panificio Bianchi", "Via della Beverara 30", "40131", 44.5150, 11.3300, ("06:30", "09:00")),
    ("Caffè Roma", "Via Mazzini 74", "40137", 44.4880, 11.3620, ("07:00", "10:00")),
    ("Market Verdi", "Via Massarenti 210", "40138", 44.4930, 11.3820, ("08:00", "13:00")),
    ("Ristorante Al Porto", "Via Murri 33", "40137", 44.4810, 11.3560, ("10:00", "12:30")),
    ("Bar Sport", "Via San Donato 60", "40127", 44.5080, 11.3650, ("07:00", "10:00")),
    ("Enoteca Corte", "Via Toscana 15", "40141", 44.4760, 11.3720, ("09:00", "12:00")),
    ("Pasticceria Dolce", "Via Corticella 120", "40128", 44.5260, 11.3480, ("06:30", "09:30")),
    ("Osteria Vecchia", "Via Zanardi 92", "40131", 44.5120, 11.3220, ("10:00", "12:00")),
    ("Market Sole", "Via Ferrarese 155", "40128", 44.5200, 11.3600, ("08:00", "12:00")),
    ("Bar Stazione", "Via Stalingrado 45", "40128", 44.5150, 11.3730, ("07:00", "10:00")),
    ("Gelateria Riva", "Via Emilia Ponente 180", "40133", 44.5010, 11.2950, ("10:00", "13:00")),
    ("Pizzeria Napoli", "Via Bovi Campeggi 8", "40131", 44.5060, 11.3380, ("10:00", "12:00")),
    ("Hotel Miramare", "Via Emilia Levante 22", "40139", 44.4830, 11.3900, ("07:30", "11:00")),
]
for i, (nome, via, cap, lat, lon, (a, b)) in enumerate(C, 1):
    db.add(Customer(user_id=uid, codice_cliente=f"C{i:03d}", nome=nome, indirizzo=f"{via}, {cap} Bologna BO",
                    comune="Bologna", provincia="BO", cap=cap, lat=lat, lon=lon, indirizzo_geocodificato=f"{via}, {cap} Bologna BO",
                    stato_geocodifica="verificato", affidabilita_geocodifica=1.0, fonte_geocodifica="manuale",
                    scarico_mattina_da=dt.time.fromisoformat(a), scarico_mattina_a=dt.time.fromisoformat(b),
                    tempo_scarico_min=10, ztl=(i in (1, 2)), sponda=(i in (4, 8))))
db.commit()
print("seed ok")
