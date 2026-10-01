# Ottimizzazione distanza-prima — 1 ottobre 2026

> Per la ricerca oltre 8 fermate, budget e nuovi benchmark vedere
> [optimizer-scaling.md](optimizer-scaling.md). Le priorità qui descritte restano valide.

Le soluzioni fattibili sono confrontate lessicograficamente per chilometri totali, durata totale, attese e numero di avvisi. Il rientro, quando richiesto, entra nei totali. Il confronto usa valori non arrotondati: anche una piccola differenza di distanza precede il tempo, senza pesi o tolleranze arbitrarie. A consumo costante per mezzo, ridurre i km riduce anche energia e costo; le formule economiche non cambiano.

La fattibilità precede sempre i km. Per soluzioni impossibili resta il confronto storico: ritardo totale, numero di violazioni, score storico. Lo score numerico resta per diagnostica e benchmark storici; non decide fra percorsi fattibili. ZTL e sponda mantengono il ruolo esistente di avvisi, la capacità viene validata prima del routing e non viene aggiunto un vincolo orario di rientro assente dal modello.

Il greedy confronta fattibilità, km della tappa, viaggio più attesa, attesa e chiusura della finestra. Per la medesima tappa sceglie il primo servizio fattibile, così una finestra successiva non introduce attesa evitabile. Le priorità di carico dello score storico non possono superare fattibilità o distanza. Enumerazione, swap, 2-opt, relocate e confronti fra seed/ordine operatore condividono `solution_key`.

Fino a 8 fermate si enumerano tutti gli ordini. Sopra 8 la ricerca resta euristica: priorità garantita fra candidati esaminati, non ottimo globale garantito. Il fallback fino a 15 fermate conserva la prova di fattibilità con completamento anticipato per stato, non promette il minimo di distanza del testimone. I seed esistenti restano deterministici e sono valutati con il nuovo obiettivo.

OSRM Table e cache indipendente da data/orario continuano a fornire la matrice. Mapbox non viene chiamato per scegliere l'ordine; arricchisce soltanto il percorso finale. Nessun cambiamento a UI, storico, programmazione, refresh o formule dei consumi.

Directions `driving-traffic`: default e massimo portati a 25 coordinate, inclusi deposito e rientro. Verifica sulla [documentazione ufficiale Mapbox](https://docs.mapbox.com/api/navigation/directions/) del 1 ottobre 2026. Il limite di 10 della Matrix API non riguarda Directions. Restano configurabili segmenti più piccoli, con un punto condiviso, senza duplicare tratte e con partenze comprensive di scarichi/attese.

## Evidenza dei test

- `test_optimizer_distance_first.py`: meno km anche con score storico peggiore e più minuti, con/senza finestre e rientro; parità km; differenze sotto l'arrotondamento visualizzato; rientro decisivo; greedy e local search su 9/16 fermate; fattibilità assoluta anche con carico estremo.
- Test esistenti conservati per finestra violata contro percorso fattibile, capacità, fallback, ricalcolo manuale e lateness. I confronti di qualità delle euristiche usano ora la chiave effettiva. L'oracolo storico a pesi rimane esplicitamente storico: il test esaustivo confronta il nuovo risultato con un minimo indipendente `(km, minuti)`.
- Routing: segmenti a 25/26/51 punti, cap anche con configurazione 100, override a 10; copertura di tutte le tratte, ordine invariato e fallback. Consumi e costi verificati su 2 e 3 km per gasolio, benzina, elettrico e plug-in. Test HTTP esistenti verificano zero Mapbox durante `/optimize` e ordine invariato dopo arricchimento.

I report benchmark precedenti restano snapshot storici; non rappresentano misure dell'obiettivo nuovo e non dimostrano risparmi su giri reali.

## Verifica locale

Suite completa con Python della `.venv`: **265 passed, 2 skipped** (139,48 s). Dopo l'estensione energia a 2/3 km e la rifinitura dei candidati impossibili: **65 test mirati passati** (21,14 s). JavaScript: **25 passed**. Build `docker build -t girofacile-test .`: completata. `git diff --check`: pulito.

La prima esecuzione standard ha incontrato 83 errori di setup dovuti ai permessi della cartella temporanea preesistente di pytest. La suite completa è stata quindi eseguita con `-p no:cacheprovider --basetemp=<cartella nuova>` senza cambiare ACL o test. Il Python di sistema non contiene pytest: utilizzato l'ambiente virtuale del repository. I due skip richiedono `TEST_POSTGRES_URL` (integrazioni routing PostgreSQL e backup/restore). Restano warning di deprecazione preesistenti.
