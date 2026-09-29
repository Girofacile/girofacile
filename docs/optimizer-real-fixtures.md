# Validazione offline dei giri anonimizzati

Non sono stati forniti giri reali: le directory `tests/fixtures/optimizer_real/development` e `validation` sono vuote. I risultati JSON allegati attestano count=0, non un miglioramento reale.

## Preparazione

Raccogliere 15-20 giri, anonimizzare deposito e clienti con ID non riconducibili a persone, eliminare indirizzi, coordinate, nominativi e altri metadati sensibili. Conservare le matrici complete direzionali km/minuti acquisite nello stesso contesto, l'ordine realmente deciso dall'operatore, partenza, finestre e durata scarico. Nessuna chiamata Google/OSRM viene eseguita durante il benchmark.

Separare prima del tuning i giri in due insiemi senza duplicati o copie dello stesso giro:

- `development`: utilizzabile per migliorare l'algoritmo.
- `validation`: holdout, da aprire solo per valutare la versione finale congelata; non scegliere pesi o modificare l'algoritmo usando questi risultati. Dopo tuning sul holdout serve un nuovo holdout indipendente.

Un file JSON per giro nella directory appropriata. Non cambiare `source` a un esempio sintetico per farlo sembrare reale. Il runner verifica la struttura, non può attestare la provenienza reale o l'anonimizzazione.

## Formato versione 1

Questo è esclusivamente un esempio sintetico di formato, non una fixture reale:

```json
{
  "schema_version": 1,
  "source": "synthetic_test",
  "scenario_id": "esempio-sintetico",
  "split": "development",
  "depot": {"id": "D0"},
  "start_time": "08:00",
  "return_depot": true,
  "stops": [
    {"id": "C1", "service_min": 15, "scarico_mattina_da": "09:00", "scarico_mattina_a": "12:00", "ztl": false, "sponda": true},
    {"id": "C2", "service_min": 10, "scarico_pomeriggio_da": "14:00", "scarico_pomeriggio_a": "17:00"}
  ],
  "operator_order": ["C2", "C1"],
  "matrix_km": [[0, 10, 14], [11, 0, 8], [13, 9, 0]],
  "matrix_min": [[0, 20, 35], [24, 0, 15], [29, 18, 0]],
  "metadata": {"note": "solo esempio sintetico"},
  "energy": {"currency": "EUR", "components": [{"consumption_per_100km": 12, "price_per_unit": 1.8}]}
}
```

Per dati reali anonimizzati usare `source: "anonymized_real"`. Da 1 a 15 fermate, ID stringa univoci e `operator_order` permutazione completa. Le matrici hanno dimensione N+1: indice 0 deposito, indici 1..N nell'ordine dell'array `stops`, indipendentemente dall'ordine operatore. Celle km/minuti finite e non negative, diagonale zero; sono ammesse asimmetrie e tempi non proporzionali alle distanze. Non sono ammesse celle mancanti: il runner non le completa online.

Orari validi della stessa giornata; ciascuna finestra richiede entrambi gli estremi. Finestre assenti/null significano assenza del vincolo. `00:00` è un orario valido. `service_min` è la durata dello scarico (default 0). `ztl` e `sponda` sono avvisi booleani, non vincoli rigidi. `label` e `metadata` sono facoltativi e devono essere anonimi. Deposito e metadati non influiscono sul calcolo, che usa le matrici. Rientro e orario di partenza sono obbligatori.

Energia facoltativa: per diesel usare litri/100 km e prezzo/litro; per elettrico kWh/100 km e prezzo/kWh. Per plug-in si possono sommare componenti coerenti con i consumi effettivi stimati. Costo = km × somma(consumo/100 × prezzo). È una stima proporzionale alla distanza, non include attesa, pedaggi o costo personale. Senza dati il costo è null.

## Esecuzione

Dall'ambiente Python del progetto:

```text
python tests/run_real_optimizer_benchmark.py --split development --output docs/optimizer-real-development-results.json
python tests/run_real_optimizer_benchmark.py --split validation --output docs/optimizer-real-validation-results.json
```

`--root PERCORSO` permette di tenere dati e risultati fuori dal repository. `--allow-synthetic` è solo per prove tecniche esplicite su esempi sintetici; non abilitarlo nella validazione reale. Il runner legge solo il gruppo richiesto e rifiuta split incoerenti/ID duplicati nello stesso gruppo. L'assenza di file produce un report valido con conteggio zero e statistiche null.

Ogni record confronta ordine operatore e GiroFacile: km, durata totale (viaggio+attesa+scarico+rientro se attivo), score storico, violazioni, ritardo totale e attesa, ordine ottenuto, delte assolute e percentuali km/minuti, costi opzionali. Delta = GiroFacile − operatore: negativo significa riduzione; percentuali null se il valore iniziale è zero. Migliorato/invariato/peggiorato usa la priorità fattibilità, ritardo, conteggio, score; può quindi essere migliore anche percorrendo più km. Riepilogo con media/mediana/min/max delle delte, ID dei casi migliori/peggiori per km, conteggi e regressioni di fattibilità (fattibile → non fattibile), oltre all'aumento del numero di violazioni. L'ordine operatore è una baseline, non un ottimo.

I risultati dei test sintetici non dimostrano risparmi reali. Per avviare la validazione mancano i 15-20 giri anonimizzati completi e la suddivisione congelata dei due gruppi.
