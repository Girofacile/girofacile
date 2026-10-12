> Aggiornamento 12 ottobre 2026: per Shopify, WooCommerce e inoltro email vedere [collegamenti automatici](order-connectors.md), con requisiti di attivazione e limiti.

> **Politica aggiornata (12 ottobre 2026):** gli ordini importati sono entità
> autonome e non vengono mai associati ai Clienti di GiroFacile, nemmeno con
> nome e indirizzo identici. Il campo `external_customer_id` resta un
> riferimento originario del gestionale, non crea alcuna relazione anagrafica.
> Non vengono ereditati indirizzi, orari, sponda, transpallet, note o
> verifiche geografiche da Clienti. Per pianificare è necessaria la verifica
> dell'indirizzo contenuto nell'ordine; le informazioni aggiuntive sono
> facoltative. Le tabelle storiche di mapping restano conservate per
> compatibilità con i database esistenti, ma non vengono più utilizzate.
>
# Invio ordini a GiroFacile

## Configurazione iniziale

Il titolare apre Ordini → Collega i tuoi ordini → Configura gestionale, indica nome/software e sceglie API standard. Carica un campione JSON reale anonimizzato, controlla le associazioni proposte, verifica e attiva la fonte. Il campione **non importa ordini**. Il titolare genera quindi una credenziale dedicata; viene mostrata una sola volta. Copiarla nel gestore segreti del gestionale, mai in file pubblici o URL. Il gestionale deve implementare l'invio: lo stato Attiva indica disponibilità dell'endpoint, non certifica un collegamento con il fornitore.

Comunica al tecnico: URL HTTPS dell'installazione, nome/versione del gestionale, esempio del tracciato, identificativi stabili di ordini/clienti, associazioni dei campi e frequenza prevista. Nessun connettore proprietario universale, accesso email o sincronizzazione e-commerce è incluso.

## Richiesta standard

`POST https://<installazione>/api/order-ingestion`

Headers: `Content-Type: application/json` e `Authorization: Bearer <CREDENZIALE_DELLA_FONTE>`.

```json
{
  "batch_id": "export-20261011-0001",
  "dry_run": false,
  "orders": [{
    "external_id": "ORD-00001",
    "number": "2026/00001",
    "external_customer_id": "CLI-001",
    "recipient_name": "Destinatario di esempio",
    "delivery_address": "Via Roma 1, Milano",
    "requested_date": "2026-10-20",
    "time_from": "09:00",
    "time_to": "12:00",
    "packages": 3,
    "weight_kg": 12.5,
    "pallets": null,
    "volume_m3": null,
    "tail_lift": false,
    "pallet_truck": null,
    "ztl": null,
    "requirements": null,
    "notes": "Citofonare al magazzino",
    "items": [{"sku": "ART-1", "description": "Articolo esempio", "quantity": 3}]
  }]
}
```

Esempio tecnico Python (URL/token da variabili d'ambiente; non stampare il token):

```python
import json, os, urllib.request
with open("ordini.json", encoding="utf-8") as f:
    body = json.load(f)
request = urllib.request.Request(
    os.environ["GIROFACILE_URL"].rstrip("/") + "/api/order-ingestion",
    data=json.dumps(body).encode(), method="POST",
    headers={"Content-Type": "application/json",
             "Authorization": "Bearer " + os.environ["GIROFACILE_SOURCE_TOKEN"]},
)
with urllib.request.urlopen(request, timeout=60) as response:
    report = json.load(response)
    print(report["id"], report["status"], report["report"])
```

## Contratto e recupero errori

- `external_id` e `number`: stringhe non vuote, massimo 160 caratteri. L'identificativo è univoco **nella fonte aziendale**. Mantenerlo stabile; stesso codice in una fonte diversa rappresenta un altro ordine. I codici con zeri iniziali devono essere testo anche in Excel.
- `batch_id`: stringa di 1–140 caratteri, lettere, numeri, `_ . : -`. Stesso batch e stesso contenuto restituiscono lo stesso report senza ripetere l'acquisizione. Stesso batch con contenuto diverso: 409. Anche un esito fallito è memorizzato: correggere i dati e utilizzare un nuovo batch. Dopo timeout ritentare prima lo stesso batch.
- Ogni ordine è una **fotografia completa**, non una modifica parziale: i campi opzionali omessi diventano mancanti nell'ultimo invio. Le correzioni operative che differiscono dal precedente invio sono conservate. Il primo ordine ricevuto resta immutabile e gli aggiornamenti sono registrati nello storico.
- Nuovi ordini e aggiornamenti passano a Da verificare. Nessuna geocodifica o pianificazione automatica. Indirizzo, destinatario e peso mancanti sono avvisi; altri errori di formato impediscono l'intero lotto. `false` è distinto da un campo assente.
- Un ordine assegnato a un giro, avviato, chiuso o annullato non viene aggiornato: errore e rollback dell'intero lotto. Ripetere dati identici è innocuo anche per un ordine bloccato.
- `dry_run: true` valida senza creare/aggiornare ordini. La prova viene registrata e non consuma il batch_id. L'attivazione iniziale usa invece il campione guidato prima dell'emissione della credenziale.
- Campi standard opzionali possono essere aggiunti dopo il campione. Alias del gestionale richiedono associazioni salvate. Campi sconosciuti non associati sono rifiutati. Per `items`, inviare un elenco con descrizione e quantità, SKU facoltativo.
- Limiti: 2 MB JSON, 1–1000 ordini, massimo 500 articoli/ordine, 60 richieste/minuto/fonte. Difesa aggiuntiva 120 tentativi/minuto/IP per processo e memoria limitata; configurare anche limiti globali al proxy per installazioni con più worker. Usare il proxy fidato configurato nell'app; non fidarsi di header IP arbitrari.
- 200: report (`completed` oppure `preview_ready` per prova). 401: credenziale assente/non valida/revocata. 403: fonte sospesa o piano non attivo. 409: conflitto batch/configurazione. 413: dimensioni. 422: formato o lotto fallito; nessun ordine del lotto modificato. 429: attendere `Retry-After` (60 secondi).
- I report includono ID, stato, conteggi, errori per riga e primi 100 risultati. Lo storico aziendale permette di consultare le pagine successive. In caso di errore interno comunicare l'ID report all'assistenza, senza credenziali.
- Ruotare la credenziale invalida immediatamente la precedente. Revocarla sospende la fonte; per riprendere, riattivare e generarne una nuova. Rimuovere la fonte conserva ordini e storico ma impedisce la riattivazione.

## File CSV / XLSX

Stesso percorso con modalità File: caricare, associare colonne, verificare, attivare e **Conferma importazione**. CSV UTF-8 (anche BOM) o Windows-1252, separatore virgola/punto e virgola/tab; XLSX singolo foglio, senza formule, macro o collegamenti esterni. Massimo 2 MB, 1000 righe, 50 intestazioni univoche e celle di 5000 caratteri. Decimali con virgola e Sì/No sono riconosciuti. Date ISO o GG/MM/AAAA; fasce orarie complete e ordinate.

Ripetere un file con gli stessi identificativi e contenuti non duplica ordini. Correzioni delle associazioni richiedono una nuova verifica e attivazione. L'anteprima scade dopo 24 ore; i campioni completati vengono eliminati subito, quelli scaduti al prossimo caricamento aziendale. Gli ordini e i report restano nell'archivio. Una modifica concorrente dopo l'anteprima blocca l'importazione e richiede una nuova verifica.
