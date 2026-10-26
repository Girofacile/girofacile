# Changelog

Le note delle versioni tecniche precedenti (V87–V89.7) sono in [docs/storico](docs/storico/).
Da qui in avanti le modifiche si annotano in questo file, la più recente in alto.

## Verso la V1

- "Controlla la suddivisione" come le altre pagine: titolo e sottotitolo nella
  barra in alto, freccia per tornare alla pianificazione e "Pianifica giri"
  accanto alla campanella; a giri programmati il titolo mostra l'etichetta
  "Giri programmati".
- "Controlla la suddivisione": quando si sposta una consegna fra i giri non
  compare più l'avviso giallo in alto ("Ricalcolo necessario" / "Suddivisione
  manuale"). Compare solo la barra in basso, ora con il tasto "Ripianifica
  giri" (prima "Ricalcola assegnazioni") e "Annulla modifiche". Resta l'avviso
  dei giri in bozza se la programmazione non si completa.
- "Controlla la suddivisione": tolti i due avvisi grandi in alto (riepilogo
  della distribuzione e clienti fuori orario). Le consegne fuori orario e non
  assegnate restano in "Da sistemare"; restano gli avvisi di ricalcolo e di
  bozza non programmata.
- Pianificazione con più mezzi: sparisce il riquadro "Costo del giro" (il
  prezzo del carburante si imposta già in ogni card del mezzo, in "Costi
  carburante ed energia") e la mappa "Dove sono i clienti" prende tutta la
  larghezza. Anche la barra in basso non mostra più il carburante. Con un solo
  mezzo non cambia nulla.
- Più mezzi, "Controlla la suddivisione": nuovo layout. In alto la tabella di
  confronto dei giri (autista, mezzo, fermate, km, costo, rientro, avvisi);
  sotto il giro scelto con la mappa (gli altri giri attenuati, un colore per
  giro come l'avatar) e le fermate in ordine, con sponda, ZTL e fuori orario
  come etichette. A destra "Da sistemare" elenca solo le consegne non assegnate
  e quelle fuori orario; «Assegna al giro N» sposta una non assegnata nel giro
  che si sta guardando. Le fermate si trascinano sulla riga di un altro giro.
- Profilo account: finestra più compatta a due colonne. A sinistra avatar,
  ruolo, nome, email e password; a destra il piano con stato, barre di
  utilizzo e i pulsanti Gestisci piano e Fatturazione. Niente più "Salva
  profilo": come in Profilo azienda la barra "Salva modifiche" compare solo
  dopo una modifica; chiudere senza salvare annulla le modifiche.
- Sidebar: la pagina misura lo spazio libero e ingrandisce le voci (36, 40, 44
  o 48 px, testo più grande da 40 px) senza mai far comparire la barra di
  scorrimento; si ricalcola quando si apre o chiude un gruppo e quando cambia
  la finestra. Se non c'è posto nemmeno con voci da 32 px, il riquadro di
  upgrade si nasconde.
- Sidebar: in fondo un riquadro blu invita al piano successivo (Starter →
  Business, Business → Pro) e apre Piani e abbonamento. Non compare con Pro,
  per i collaboratori e quando è aperto "Azienda e sistema". Nuovo componente
  `.gf-sidebar-upgrade` nel catalogo.
- Anteprima giro (un mezzo): pagina ridisegnata come il dettaglio dei giri
  programmati. Testata con nome e stato, numeri con icone, tabella delle
  fermate in alto e, sotto, mappa con autista, mezzo, costi, avvisi "Prima
  della partenza" e "Programma giro". Stampa e spiegazione AI in "Altre azioni".
- Corretto: la barra di navigazione del telefono compariva anche su computer,
  per due chiusure in più lasciate nella pagina Fatturazione.
- Fatturazione: pagina ridisegnata. In alto il prossimo addebito con stato,
  carta, email per le fatture e ultimo pagamento (niente più fila di quattro
  riquadri); fatture e pagamenti in un pannello a schede; dati fiscali in
  lettura con "Modifica" e barra di salvataggio, e controllo dei dati per la
  fattura elettronica. Tolto il riquadro "Notifiche di pagamento", che
  indicava come attivi invii email non presenti.
- Piani e abbonamento: pagina ridisegnata. In alto il piano attuale con stato,
  prezzo, scadenza e consumi del mese; sotto tre card da scegliere con limiti e
  funzioni (✓ incluse, ✕ non incluse; firma, foto e prova di consegna in una
  sola voce), confronto completo apribile e barra flottante per il cambio piano.
- Portale autista: senza rete gli esiti (consegnata, mancata, nota) restano
  salvati sul telefono, compaiono subito nel giro e partono da soli quando la
  connessione torna. Un riquadro indica quanti esiti attendono l'invio.
- Ordini: tolta dalle fonti la scheda "Email", non ancora disponibile. Shopify,
  WooCommerce, file e API standard restano attivi.
- Configurazione: aggiunto `.env.example` con tutte le impostazioni del server.
- Repository: changelog storici spostati in `docs/storico`.
- Produzione: l'avvio si blocca anche con SQLite, `APP_BASE_URL` non https o
  archivio prove di consegna locale/incompleto; email, avvisi errori e altre
  impostazioni mancanti compaiono come avvisi nel log.
- Produzione: nuovo `/health` (app + database), healthcheck Docker, proxy HTTPS
  Caddy in `deploy/caddy` e guida in `deploy/README.md`.
