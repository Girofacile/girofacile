# GiroFacile: avvisi informativi ZTL e area pedonale

GiroFacile mostra **due soli avvisi non bloccanti** per indirizzi con coordinate verificate:

- **Attenzione: cliente in zona ZTL.** Verifica le condizioni di accesso.
- **Attenzione: cliente in area pedonale.** Verifica le modalità di consegna.

Non sono condizioni di fattibilità: **non modificano ordine delle fermate, punteggi,
criteri di raggruppamento, distanza, orari né accesso del mezzo**. Non indicano permessi
o deroghe, né sono una certificazione giuridica. Una ZTL può essere attiva solo in certi
giorni/orari; l'avviso resta volutamente informativo.

## Fonti e copertura

- **ZTL OSM:** geometrie con `boundary=limited_traffic_zone`.
- **Aree pedonali OSM:** superfici poligonali `highway=pedestrian + area=yes`,
  `area:highway=pedestrian` e multipoligoni pedonali. Escludiamo
  `highway=footway` e vie mappate solo come linee: una linea senza larghezza non
  dimostra che un indirizzo cada al suo interno. Queste esclusioni possono produrre
  falsi negativi, ma evitano di confondere marciapiedi e aree pedonali.
- **GeoJSON comunali opzionali:** `ztl_official.geojson` e
  `pedestrian_official.geojson` nella stessa cartella; vengono interrogati per
  primi quando presenti, con fallback OSM. Inserire **solo** dati pubblicati e
  riutilizzabili commercialmente secondo la specifica licenza. GiroFacile non
  scarica né presume disponibili automaticamente i dati dei Comuni.

Un punto non trovato significa **"nessuna limitazione rilevata nei dati presenti"**,
non "accesso libero". Una posizione non verificata o un archivio mancante produce
`non_disponibile`, distinto da `non_rilevata`. Ogni fonte può essere incompleta
o non aggiornata. In particolare, i dati OSM non garantiscono tutte le ZTL d'Italia.

Le geometrie sono memorizzate una volta per installazione, sono condivise fra
aziende e **non contengono indirizzi, utenti o clienti**. La geocodifica Google
di indirizzi non viene ripetuta per queste segnalazioni; si usano solo coordinate
già acquisite durante il normale flusso di verifica cliente/ordine.

## Prima attivazione e aggiornamenti

In locale Windows (dalla cartella di GiroFacile):

```powershell
.\.venv\Scripts\python.exe -m scripts.update_ztl_osm
```

Il comando aggiorna **entrambi** gli archivi locali indipendenti:

- `data/ztl/ztl_osm.geojson`
- `data/ztl/pedestrian_osm.geojson`

**Importante per installazioni preesistenti:** se il BAT controlla soltanto
l'età di `ztl_osm.geojson` e questo è recente, non scaricherà l'archivio pedonale
fino al successivo ciclo settimanale. Eseguire il comando sopra **una volta**
dopo l'aggiornamento; non occorre modificare il BAT.

In Docker Compose, l'updater separato `ztl-updater` richiama lo stesso script
all'avvio e ogni **sette giorni**, con riprova a 12 ore in caso di errore. L'app
e l'updater condividono `./data/ztl`. In caso di download fallito l'archivio
precedente resta intatto; le altre funzionalità di GiroFacile continuano a operare.

Lo scarico usa Overpass pubblico con due query distinte e rispettose delle
limitazioni del servizio; nessuna richiesta esterna viene effettuata durante la
pianificazione. Gli endpoint possono essere configurati con
`GF_ZTL_OVERPASS_URL` e `GF_ZTL_USER_AGENT`. Sono ammessi percorsi alternativi
tramite `GIROFACILE_ZTL_GEOJSON`, `GIROFACILE_PEDESTRIAN_GEOJSON`,
`GIROFACILE_ZTL_OFFICIAL_GEOJSON` e `GIROFACILE_PEDESTRIAN_OFFICIAL_GEOJSON`.

## Visualizzazione e storicizzazione

- **Anagrafica:** badge ZTL e area pedonale vicino all'indirizzo e nel dettaglio.
- **Verifica:** al momento in cui la posizione viene verificata si memorizza
  l'indicazione pedonale sul cliente. Le API la ricalcolano anche quando cambia
  l'archivio, così una nuova mappa aggiorna i badge senza nuove chiamate Google.
  Il flag ZTL manuale dell'anagrafica resta separato dal rilevamento automatico.
- **Ordini:** i due avvisi vengono calcolati sulle coordinate confermate
  indipendentemente da eventuali associazioni ordine-cliente.
- **Pianificazione / riepilogo:** due badge separati, avvisi in anteprima e
  indicatori salvati sulle fermate dei giri. Gli avvisi non bloccano la creazione
  del giro o le opzioni di ottimizzazione.

## Licenze

© OpenStreetMap contributors, Open Database License (ODbL 1.0),
https://www.openstreetmap.org/copyright. Conservare l'attribuzione e valutare
gli obblighi della ODbL qualora si distribuiscano banche dati derivate.
Ogni GeoJSON comunale conserva la propria licenza ed eventuali condizioni
di attribuzione, che vanno verificate separatamente prima di installarlo.

## Test

```bash
python -m pytest tests/test_ztl_detection.py tests/test_pedestrian_detection.py -q
```

Il primo caso reale consigliato è Piazza Giovanni Leone 22 a Pomigliano d'Arco.
**Non si può affermare che risulti rilevata senza aver verificato l'archivio
effettivo e le coordinate precise dell'indirizzo geocodificato**.
