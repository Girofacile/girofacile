# GiroFacile: clienti raggiungibili solo in traghetto

Fino alla V1 GiroFacile **non pianifica le consegne che richiedono un traghetto**.
Il calcolo stradale (OSRM, mappe OpenStreetMap) tratta le linee dei traghetti come
strade sempre aperte: niente orari delle corse, attesa, imbarco né biglietto. Una
prova del 1° novembre 2026 ha dato 262 minuti da Pozzuoli a Ischia Porto (nave a
circa 5 km/h, cambio di nave a Procida) e 29 minuti con il calcolo di riserva in
linea d'aria: tempi inutilizzabili in entrambi i casi.

## Comportamento

- Il controllo confronta la terra del **deposito** con quella del **cliente**. Se
  sono diverse la consegna resta fuori dal giro: deposito a Napoli e cliente a
  Ischia, ma anche deposito a Messina e cliente a Reggio Calabria. Deposito e
  cliente sulla stessa isola (Catania e Palermo, Ischia Porto e Forio) si
  pianificano normalmente.
- **Giro singolo** (dashboard e app mobile): la consegna viene tolta dal giro e
  compare negli avvisi dell'anteprima come «Consegna non programmabile: cliente
  su un'isola». Il suo peso non conta per la capacità del mezzo. Se tutte le
  consegne sono oltre il mare il calcolo si ferma con un messaggio.
- **Più mezzi**: la consegna è esclusa prima della ricerca, risulta tra le non
  assegnate («Da sistemare», badge «Solo in traghetto») e il primo avviso del
  piano la elenca. Anche se assegnata a mano resta fuori; per confermare il piano
  si spunta la conferma delle consegne non assegnate.
- Gli ordini importati di queste consegne restano da pianificare.

## Dati

`app/data/isole_traghetto.geojson`: contorni OpenStreetMap (ODbL) semplificati
tramite Nominatim, 43 isole: golfo di Napoli, isole pontine e toscane, Sicilia e
isole minori, Sardegna e isole minori, Tremiti, laguna di Venezia, Monte Isola e
isole Borromee. Le isole unite da ponte stradale hanno lo stesso `group` della
terra a cui sono collegate (Ortigia → Sicilia, Sant'Antioco → Sardegna,
Caprera → La Maddalena, Mazzorbo → Burano). Venezia centro storico non è
nell'elenco perché è collegata da ponte (Piazzale Roma). Un margine di 150 m
compensa la semplificazione dei contorni sulle banchine dei porti.

## Dopo la V1

È prevista una sezione per le linee e i biglietti dei traghetti (porti, orari
delle corse, durata, anticipo d'imbarco, costo): in pianificazione la traversata
diventerà una tratta a orario e queste consegne torneranno pianificabili.
