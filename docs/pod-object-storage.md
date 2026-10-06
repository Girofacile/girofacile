# POD con Object Storage privato

Firma, foto e PDF nuovi non vengono salvati come blob nel database. PostgreSQL
conserva soltanto chiavi, MIME, dimensioni, SHA-256 e date; `signature_data`
resta disponibile soltanto per le firme legacy. Nessuna migrazione cancella le
firme esistenti.

In produzione GiroFacile usa storage S3-compatible privato (ad esempio Hetzner
Object Storage). In sviluppo locale può usare un backend filesystem dedicato,
senza Docker e senza servizi esterni.

## Sviluppo locale senza Hetzner e senza Docker

Per provare firma, foto e PDF POD sul PC locale impostare nel file `.env`:

```dotenv
APP_ENV=development

OBJECT_STORAGE_ENABLED=true
OBJECT_STORAGE_BACKEND=local
OBJECT_STORAGE_LOCAL_PATH=data/pod_storage
OBJECT_STORAGE_LOCAL_SECRET=una-stringa-locale-lunga-e-casuale
OBJECT_STORAGE_SIGNED_URL_SECONDS=900
```

`OBJECT_STORAGE_LOCAL_PATH` può essere relativo alla cartella del progetto.
I file vengono salvati sotto:

```text
data/pod_storage/
  companies/
    <azienda>/
      routes/
        <giro>/
          deliveries/
            <consegna>/
              signature-....png
              delivery_photo-....jpg
              pod-....pdf
```

Questa cartella è esclusa da Git.

Per verificare la configurazione:

```powershell
.venv\Scripts\python.exe -m app.services.object_storage
```

Il risultato atteso è:

```text
Archivio POD configurato e verificato: local
```

Non serve Docker Desktop e non serve MinIO.

Quando dalla Dashboard o dal portale si apre una firma, una foto o un PDF,
GiroFacile genera un link temporaneo firmato HMAC valido per pochi minuti e
serve il file attraverso il backend stesso. Il browser del telefono può quindi
aprire il documento usando lo stesso host con cui sta già raggiungendo GiroFacile
(es. `http://192.168.x.x:8000`), senza configurare un secondo endpoint.

Il backend locale è accettato soltanto in `development/dev/test`. Se
`APP_ENV=production`, GiroFacile lo rifiuta.

## Configurazione produzione Hetzner

In produzione usare:

```dotenv
OBJECT_STORAGE_ENABLED=true
OBJECT_STORAGE_BACKEND=s3
OBJECT_STORAGE_ENDPOINT=https://<endpoint-object-storage>
OBJECT_STORAGE_REGION=<regione>
OBJECT_STORAGE_BUCKET=<bucket-privato>
OBJECT_STORAGE_ACCESS_KEY=<access-key>
OBJECT_STORAGE_SECRET_KEY=<secret-key>
OBJECT_STORAGE_SIGNED_URL_SECONDS=900
```

Il bucket deve restare privato. Il backend verifica ACL/policy e genera
presigned URL temporanei. Le credenziali non devono essere inserite nel
repository o nei log.

Prima del deploy:

```bash
python -m app.migrations
python -m app.services.object_storage
```

## Comportamento e limiti

- Le nuove firme non vengono più salvate in `signature_data`.
- Foto JPEG/PNG/WebP: massimo 12 MB in ingresso e 24 megapixel.
- Le foto vengono ridimensionate fino a 1600 px e ricodificate JPEG qualità 82.
- Le firme vengono normalizzate in PNG.
- EXIF/GPS delle foto vengono rimossi.
- Il PDF POD contiene dati consegna, firma e foto quando presenti.
- SHA-256 verifica l'integrità dei file ma non costituisce firma digitale qualificata.
- I link temporanei scadono dopo 60-900 secondi.
- Il backend verifica sempre ownership prima di emettere il link al documento.
- Le vecchie firme Base64 restano leggibili per compatibilità.
- Se la prova obbligatoria non può essere salvata, la consegna non viene chiusa.

## Backup

Il backup PostgreSQL contiene soltanto i riferimenti ai file. In produzione va
quindi previsto anche il backup/versioning del bucket Object Storage.

In locale, la cartella `data/pod_storage` contiene le prove POD di sviluppo e
può essere cancellata se si vuole azzerare esclusivamente lo storage locale di test.

## Test

```bash
python -m pytest tests -q
node --test tests/*.cjs
docker build -t girofacile-pod-check .
```

I test automatici non usano servizi esterni reali.
