# Turni e pause degli autisti

Nella scheda autista, “Turno abituale e pause” permette di impostare inizio e fine turno e fino a otto pause a orario fisso. Gli orari sono locali e riferiti alla stessa giornata: turni notturni a cavallo della mezzanotte e calendari settimanali non sono supportati. Entrambi gli estremi del turno possono restare vuoti. Le pause devono essere complete, non sovrapposte e comprese nel turno, se impostato.

In pianificazione gli orari vengono proposti dopo la scelta dell'autista. Possono essere modificati per quel giro, anche separatamente per ciascun mezzo nella suddivisione automatica. La modifica non cambia la scheda autista. Il giro conserva una copia dei propri orari; successive modifiche dell'anagrafica non alterano i giri salvati. Per eliminare le pause solo per un giro, rimuoverle dall'editor della pianificazione.

## Calcolo

Il viaggio viene interrotto durante una pausa. Uno scarico che non può finire prima della pausa viene posticipato interamente al termine del riposo. L'attesa per la finestra del cliente può sovrapporsi alla pausa senza contare due volte gli stessi minuti. Anche il rientro e il ricalcolo con traffico tengono conto delle pause.

Un giro fuori turno non può essere salvato o programmato. Nella suddivisione, le consegne incompatibili restano non assegnate. Se un aggiornamento del traffico porta un giro già salvato fuori turno, viene mostrato un avviso. Le pause compaiono tra le fermate senza diventare consegne, senza numerazione cliente o pulsanti di completamento e senza influire sui conteggi dei colli o delle consegne.

Le pause rappresentano intervalli di riposo pianificati; non individuano un parcheggio o un'area di sosta. La posizione della pausa durante una tratta non è un punto di navigazione. Gli orari sono scelti dall'operatore: questa funzione non verifica automaticamente i limiti normativi di guida e riposo.

## Persistenza e compatibilità

La migrazione additiva `20261013_02` introduce `drivers.work_schedule`, `route_plans.driver_schedule` e `route_plans.driver_breaks` (JSON nullable). I dati esistenti sono preservati; gli autisti e i giri precedenti restano senza vincoli finché l'operatore non li configura. Gli aggiornamenti dell'anagrafica tramite client precedenti che omettono `work_schedule` mantengono i valori esistenti.

I test coprono viaggio, scarico, attesa, rientro, limiti di turno, traffico, ritardo di partenza, assegnazione su più mezzi e persistenza. Il controllo browser `tests/check_driver_schedule_ui.py` usa database e servizi isolati e verifica creazione/modifica autisti e pianificazione su quattro larghezze.
