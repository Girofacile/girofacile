# Correzioni di affidabilità

La correzione di isolamento aziende del commit dbe6125 viene mantenuta.

- Firma e nome firmatario obbligatori applicati sia al portale autista sia al
  link operatore. Il link operatore ora include il riquadro firma e aggiorna
  lo stato complessivo del giro alla consegna finale.
- Limiti clienti applicati anche agli agenti e alle importazioni CSV/XLSX.
  L'importazione verifica il numero di nuovi clienti prima di modificare i dati;
  gli aggiornamenti di clienti esistenti restano consentiti al limite del piano.
- Limiti giri verificati anche nel ricalcolo manuale e prima del salvataggio;
  un giro esistente non viene contato due volte. Controllo aggiuntivo prima
  della programmazione e blocco del ricalcolo di giri avviati o chiusi.
- Capacità totale in kg e colli verificata prima del calcolo e quando si
  programma il giro. I ricalcoli manuali rispettano le impostazioni opzionali.
- Data effettiva del giro e fuso aziendale nella richiesta Google. Gli orari
  già trascorsi non vengono spostati silenziosamente a domani. Le mappe storiche
  utilizzano la geometria senza una falsa simulazione del traffico passato.
- Cache delle durate distinta per partenza, con validità di 15 minuti per il
  traffico; la modifica di un indirizzo invalida tutte le varianti temporali.
- Cartella backup comune (`BACKUP_DIR`, predefinita `backups`), compatibilità
  con archivi precedenti in `data/backups`, download .dump/.sql/.zip.
  I file parziali non vengono mostrati; ogni nuovo archivio è verificato con
  `pg_restore --list`. Password database esclusa dagli argomenti dei processi.
- Docker include script e client PostgreSQL 16; volume backup allineato.
- Report stampabile con salvataggio PDF tramite il browser; etichette corrette
  per distinguere km pianificati, ore miste e costi energetici stimati.
  Personale, pedaggi e manutenzione non sono inclusi nel costo mostrato.
- Foto prova consegna, refrigerazione e Shopify indicati esplicitamente come
  in sviluppo. Non sono nuovi servizi implementati con questa correzione.
- Rimosse le dichiarazioni duplicate di funzioni dashboard, preservando le
  ultime versioni effettivamente eseguite. Report separati in `js/reports.js`.
- Ripristinata la migrazione `agents_enabled`, rimossa accidentalmente
  nell'ultimo aggiornamento: nessuna modifica alla correzione multi-tenant.
- Aggiunta verifica automatica GitHub Actions: test, backup/ripristino su
  database PostgreSQL temporanei, controlli JavaScript e build Docker.

## Verifica e rilascio

Eseguire `python -m pytest tests -q` e `node --test tests/*.cjs`.
Per includere il test reale di backup/ripristino impostare `TEST_POSTGRES_URL`
verso un server di test. Il test crea e rimuove esclusivamente due database
temporanei con nomi casuali `gf_test_backup_*` e `gf_test_restore_*`.

Il rilascio Docker richiede la ricostruzione dell'immagine e il riavvio del
servizio. Gli asset dashboard hanno una nuova versione cache. Il backup di
produzione va verificato nell'ambiente effettivo; il test locale non certifica
credenziali, spazio disco o permessi del server del cliente.

Gli archivi restano locali: copie esterne e pianificazione automatica non
sono introdotte da questa correzione.
