# GiroFacile - Database test settori v55

Questo pacchetto contiene un database SQLite demo già popolato per testare tutte le Dashboard settoriali della v55.

## Come usarlo

1. Estrai lo ZIP.
2. Copia il file `girofacile.db`.
3. Incollalo dentro la cartella del progetto in:

```text
data/girofacile.db
```

4. Se Windows chiede conferma, sovrascrivi il database esistente.
5. Avvia GiroFacile con `start_locale_windows.bat`.

## Password comune

```text
demo1234
```

## Account admin azienda

| Settore | Username | Email | Password |
|---|---|---|---|
| Distribuzione / Cash & Carry | demo_distribution | distribution@girofacile.demo | demo1234 |
| Logistica / Corrieri locali | demo_logistics | logistics@girofacile.demo | demo1234 |
| E-commerce / Consegna ordini | demo_ecommerce | ecommerce@girofacile.demo | demo1234 |
| Food delivery / Ristorazione | demo_food | food@girofacile.demo | demo1234 |
| Servizio transfer | demo_transfer | transfer@girofacile.demo | demo1234 |
| Farmaceutico / Sanitario | demo_healthcare | healthcare@girofacile.demo | demo1234 |

## Account portale autista

| Settore | Email autista | Password |
|---|---|---|
| Distribuzione | antonio.distribution@girofacile.demo | demo1234 |
| Logistica | marco.logistics@girofacile.demo | demo1234 |
| E-commerce | giuseppe.ecommerce@girofacile.demo | demo1234 |
| Food delivery | luca.food@girofacile.demo | demo1234 |
| Transfer | salvatore.transfer@girofacile.demo | demo1234 |
| Sanitario | fabio.healthcare@girofacile.demo | demo1234 |

## Contenuto incluso

Per ogni settore sono presenti:

- 1 azienda demo collegata al settore corretto;
- 1 deposito;
- 1 mezzo;
- 1 autista con accesso al portale;
- 6 clienti/destinatari/passeggeri/punti consegna;
- 1 giro programmato;
- 1 giro in corso;
- 1 giro completato;
- stati consegna, note autista e alcune firme demo dove previste.

Nota: questo database è solo per test locale. Non usarlo in produzione.
