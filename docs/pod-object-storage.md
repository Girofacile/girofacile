# POD con Object Storage privato

Firma, foto e PDF nuovi vengono salvati in un bucket S3-compatible. PostgreSQL
conserva chiavi, MIME, dimensioni, SHA-256 e date; `signature_data` resta disponibile
soltanto per le firme legacy. Nessuna migrazione cancella le firme esistenti.
Il PDF riporta firma e foto, quando disponibili, oltre ai dati della consegna.
SHA-256 verifica l'integrità: non è una firma digitale qualificata o una certificazione legale.

## Configurazione Hetzner

1. Nella Hetzner Console selezionare il progetto dedicato a GiroFacile e aprire
   **Object Storage**. Creare un bucket con nome univoco e visibilità **Private**.
   Scegliere la località appropriata ai dati aziendali. Non attivare accesso pubblico,
   ACL pubbliche o policy con `Allow` per principal `*`.
2. Nel progetto aprire **Security -> S3 Credentials -> Generate credentials**,
   inserire una descrizione e generare le chiavi. Copiare access key e secret key:
   il secret non sarà nuovamente visualizzabile dopo la chiusura della finestra. Conservare il secret
   nel gestore di segreti del deployment, mai nel repository o nei log.
3. Usare endpoint e regione della località indicati in Console. Esempio per
   Falkenstein: endpoint `https://fsn1.your-objectstorage.com`, regione `fsn1`.
   L'endpoint non include il nome del bucket: il client usa addressing path e SigV4.
4. Impostare nell'ambiente del backend:

   ```dotenv
   OBJECT_STORAGE_ENABLED=true
   OBJECT_STORAGE_ENDPOINT=https://fsn1.your-objectstorage.com
   OBJECT_STORAGE_REGION=fsn1
   OBJECT_STORAGE_BUCKET=<nome-del-bucket-privato>
   OBJECT_STORAGE_ACCESS_KEY=<access-key>
   OBJECT_STORAGE_SECRET_KEY=<secret-key>
   OBJECT_STORAGE_SIGNED_URL_SECONDS=900
   ```

5. Le credenziali devono consentire `GetBucketAcl`, `GetBucketPolicy`, `PutObject`,
   `GetObject`, `DeleteObject`; per riconciliazione anche `ListBucket`.
   L'app verifica ACL e policy prima di upload e URL firmati. Policy pubbliche o
   permessi insufficienti causano errore 503; non vengono modificati dal codice.
6. Installare `requirements.txt`, eseguire **prima del riavvio**
   `python -m app.migrations` (nuova versione **20261004_03**) e verificare lo storage
   con `python -m app.services.object_storage`. Non eseguire la migrazione da ogni worker.
7. Dopo la verifica, nelle impostazioni aziendali attivare **Firma cliente** e/o
   **Foto prova consegna**. Quest'ultima riusa `needs_photo_proof` e rende obbligatoria
   la foto. Non richiede una nuova politica aziendale. Provare una consegna di test
   da telefono, poi visualizzare gli allegati e scaricare il PDF da desktop/mobile.

Documentazione ufficiale:
[Object Storage Hetzner](https://docs.hetzner.com/storage/object-storage/),
[creazione bucket](https://docs.hetzner.com/storage/object-storage/getting-started/creating-a-bucket/),
[generazione chiavi](https://docs.hetzner.com/storage/object-storage/getting-started/generating-s3-keys/),
[bucket privati](https://docs.hetzner.com/storage/object-storage/faq/buckets-objects/),
[URL temporanei Boto3](https://docs.aws.amazon.com/boto3/latest/guide/s3-presigned-urls.html).

## Comportamento e limiti

- Nessuna connessione allo storage all'avvio. Con storage disabilitato e nessuna prova
  richiesta, le consegne continuano a funzionare senza allegati. Il PDF viene generato
  per ogni nuova consegna completata quando lo storage è abilitato. Se prove sono
  richieste o inviate, storage assente/non disponibile impedisce il completamento.
- Foto JPEG/PNG/WebP, massimo 12 MB in ingresso e 24 megapixel; ridimensionamento
  a 1600 pixel, JPEG qualità 82, rimozione EXIF/GPS. Firme PNG ricodificate,
  massimo 1,5 MB decodificati e 4 megapixel. Il frontend conserva firma e foto in caso di errore
  finché la schermata resta aperta; non offre persistenza offline dopo chiusura/refresh.
- Chiavi generate dal server sotto `companies/{azienda}/routes/{giro}/deliveries/{id}/`,
  con UUID per evitare sovrascritture. Mai chiavi accettate dal frontend.
- Accesso aziendale, autista assegnato e token del giro controllati dal backend;
  verifica della chiave rispetto ad azienda/giro/consegna prima degli URL.
  Le API dettaglio contengono `has_signature`, `has_delivery_photo`, `has_pod`.
- URL GET temporanei, durata 60-900 secondi; PDF come attachment. Questi link
  sono credenziali temporanee: chi riceve un link può usarlo fino alla scadenza.
  Host e nome bucket sono necessariamente visibili nell'URL S3; secret key e
  configurazione completa non vengono inviati al browser. Nessun CORS è necessario
  per aprire il documento in una nuova scheda. Risposte API con `Cache-Control: no-store`.
- SHA-256 viene confrontato prima di riutilizzare allegati nel PDF. Il POD di una
  consegna completata resta immutabile nei tentativi ripetuti; la riapertura non è prevista.
- Errori storage: 503 esplicito e log `POD object storage unavailable` senza dettagli
  del provider/credenziali. Gli errori sono registrati anche nel monitoraggio SystemErrorLog esistente.
- Upload fallito o rollback: compensazione degli oggetti del tentativo, compresi PUT
  dal risultato incerto. Vecchie firme sostituite vengono eliminate solo dopo commit;
  `signature_data` legacy viene sempre preservato. Crash del processo o eliminazione
  fallita possono lasciare oggetti orfani: usare la riconciliazione descritta sotto.

## Pulizia e backup

Eseguire `python -m scripts.reconcile_pod_storage` per un report senza eliminazioni.
La scansione considera solo chiavi POD nel formato previsto e oggetti più vecchi di
48 ore. Ricontrolla i riferimenti DB sotto lock del giro prima di ogni eliminazione.
Solo dopo aver verificato il report e il corretto DB/bucket, usare
`python -m scripts.reconcile_pod_storage --delete`. Nessuna pulizia viene attivata
automaticamente. Non impostare expiration globale su `companies/`: cancellerebbe
anche prove ancora referenziate. Coordinare restore DB e restore bucket prima di
qualunque pulizia; conservare una copia recuperabile dei file secondo la politica aziendale.

Il backup PostgreSQL contiene solo riferimenti; prevedere backup/versioning del bucket
separato. Prima del deploy decidere località, durata di conservazione, backup,
periodicità della riconciliazione e aziende che richiedono firma/foto. Il codice
non crea bucket, non attiva servizi esterni e non introduce retention automatica.

## Test

`python -m pytest tests -q`; `node --test tests/*.cjs`; `docker build -t girofacile-pod-check .`.
I test POD usano `FakeStorage` esplicito, mai servizi esterni. Il test di lettura testo
PDF usa opzionalmente `pypdf` (`python -m pip install pypdf`); il generatore runtime usa ReportLab.
Su Windows usare una directory `--basetemp` nuova sotto `test-results/` se il temp
di sistema non è accessibile. Nessun test deve utilizzare il DB di produzione.

## File della modifica

Creati: `app/services/object_storage.py`, `app/services/delivery_pod.py`,
`static/pod.js`, `static/pod.css`, `scripts/reconcile_pod_storage.py`,
`tests/pod_fake.py`, `tests/test_delivery_pod.py`, `tests/test_delivery_pod_postgres.py`,
`tests/test_pod_ui.cjs`, `docs/pod-object-storage.md`.

Modificati: `app/main.py`, `app/models.py`, `app/migrations.py`,
`app/services/delivery_signature.py`, `app/services/route_execution.py`,
`app/routers/driver.py`, `app/routers/operator.py`, `app/routers/routes.py`,
`requirements.txt`, `static/driver/index.html`, `static/operator/index.html`,
`static/dashboard/index.html`, `static/dashboard/js/core.js`,
`tests/test_stability.py`, `tests/test_frontend_integrity.cjs`, `tests/test_audit_postgres.py`.

## Verifica della versione

- Suite Python completa nel container Linux, con PostgreSQL 16 temporaneo e isolato:
  **485 passati, 16 saltati**, nessun fallimento. I saltati riguardano PowerShell
  (11 casi non disponibili nel container) e OR-Tools (5 benchmark opzionali).
- Suite frontend `node --test tests/*.cjs`: **53 passati**, nessun fallimento.
- Build Docker completata sulla versione finale.
- Migrazione PostgreSQL idempotente, serializzazione, conservazione firme legacy,
  concorrenza consegne e backup/restore verificati nel database temporaneo.
- PDF dimostrativo renderizzato e controllato visivamente, una pagina con firma e foto;
  note lunghe verificate anche nel test del generatore.
- Portali autista e operatore verificati con Chrome a 390 px: foto visibile, nessun
  overflow orizzontale. Controlli desktop verificati dai test frontend condivisi.
- Il client `pg_dump` Windows è bloccato dalla policy locale di controllo applicazioni;
  il test backup/restore è stato completato nel container con i client Linux inclusi.

Non sono stati configurati bucket reali, credenziali, retention o servizi esterni.
