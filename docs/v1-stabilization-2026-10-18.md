# Stabilizzazione V1 — correzioni dell'audit del 18 ottobre 2026

Base dell'audit: `e9bab50fb2001a7023a05f345a02eac5e87cb3e6`.
Questo intervento corregge i difetti individuati nel codice; la disponibilità
generale richiede anche il collaudo operativo e infrastrutturale descritto in
[roadmap-v1.md](roadmap-v1.md).

## Checklist delle correzioni

| ID | Rilievo | Correzione e regressione richiesta |
|---|---|---|
| V1-A01 | Note/esiti avviano giri saltando data e risorse | Un'unica guardia di avvio per API esplicite e promozioni implicite; date future, risorse già occupate e recupero dei giri legacy coperti |
| V1-A02 | Apostrofi nel nome bloccano Avvia | Dati separati dal JavaScript dell'azione, test con apostrofi e virgolette nel portale autista |
| V1-A03 | Storico troncato prima dei filtri | Filtri e paginazione lato SQL, conteggio e pagine complete nei client; aziende isolate e archivi oltre 200 giri |
| V1-A04 | Ricerca oltre otto con scheduler differente | Valutazione canonica quando sono configurati turni/pause; confronto di fattibilità e durata |
| V1-A05 | Dettaglio invisibile in /mobile | Apertura della vista corretta e test del dettaglio dallo storico |
| V1-A06 | Barra flottante e navigazione si sovrappongono su tablet | Breakpoint coerente con il layout condiviso; verifica anche a 900 e 1024 pixel |
| V1-A07 | Reset password Super Admin collaboratore conserva sessioni | Sessione legata alla credenziale, reset/reinvito rendono inutilizzabili i vecchi cookie |
| V1-A08 | Link di reset alternativi e cambio email owner | Consumo/revoca dell'intera famiglia pertinente e controllo dell'identità; regressioni sui token precedenti |
| V1-A09 | Permesso manutenzione incoerente | Ogni percorso che modifica maintenance_mode richiede il permesso specifico |
| V1-A10 | Login proprio azzera tentativi su altro account | Limitazione sensibile all'identità senza azzeramento incrociato; test multi-account |
| V1-A11 | ETA spostati senza riassorbire attese | Ricalcolo operativo di finestre, scarichi e pause; mantenimento degli orari storici salvati |
| V1-A12 | Firma senza nome provoca 500 | Validazione 400 per campo omesso/null/vuoto, senza upload o persistenza parziale |
| V1-A13 | Firma PNG palettizzata perde trasparenza | Composizione RGBA su sfondo bianco, con verifica dei pixel di firma e sfondo |
| V1-A14 | Errore iniziale Storico lascia pagina vuota | Stato di caricamento, messaggio e ripetizione, senza perdere i filtri |
| V1-A15 | Formule nei nuovi export CSV | Neutralizzazione anche con prefissi di spazio e controllo; dati e colonne conservati |
| V1-A16 | Piano delle fatture rinominato dopo upgrade | Piano ricavato dai prezzi del documento o conservato dallo snapshot; documento misto esplicito, piano sconosciuto non inventato |
| V1-A17 | Modello AI sconosciuto e valuta costo incoerente | Nessuna tariffa ereditata da un altro modello, costo non stimabile e avviso; stime interne EUR etichettate EUR |
| V1-A18 | Landing promette sempre 14 giorni | Durata dal catalogo runtime, incluse prova disattivata e durata di un giorno; nessuna nuova richiesta per combinazioni |
| V1-A19 | Test riordino rosso e controlli touch mancanti | Ripristino dei pulsanti accessibili e del badge occasionale, regressione sul comportamento senza disabilitare le asserzioni |
| V1-A20 | Programmazioni concorrenti duplicano traffico | Lock e ricontrollo del risultato prima del provider; prove a sessioni separate su PostgreSQL isolato |

## Verifiche ripetibili

La pipeline [Tests and container](../.github/workflows/tests.yml) esegue backend,
JavaScript, browser, simulazioni flotta, migrazioni/concorrenza PostgreSQL,
backup/restore isolato, OSRM su dati sintetici e build dell'immagine.

Le dipendenze di test aggiuntive sono in
[requirements-v1-audit.txt](../tests/requirements-v1-audit.txt): il lettore PDF e
il risolutore di riferimento sono installati solo nel collaudo. Le dipendenze
di produzione restano invariate.

Il browser dedicato `tests/check_v1_ui_regressions.py` controlla i difetti
dell'audit a 390, 768, 900, 1024 e 1440 pixel. Log e screenshot sono conservati
negli artifact del workflow del commit effettivamente verificato.
Un test presente nel repository non equivale a un test eseguito: per l'esito
fa fede la relativa esecuzione CI, inclusi gli eventuali skip e fallimenti.

## Compatibilità e comportamenti aggiornati

- Nessuna modifica ai prezzi, alle quote commerciali, ai bonus elettrici o agli
  obiettivi dell'ottimizzatore. ZTL e sponda restano preferenze con avvisi.
- Il riordino completo fino a otto fermate rimane locale al gruppo e al mezzo.
  Questa correzione non introduce un risolutore globale né uno SLA di sette secondi.
- Nuove modifiche operative non possono avviare un giro futuro o in conflitto;
  le ripetizioni degli esiti e il recupero dei giri già avviati restano supportati.
- L'elenco storico mantiene una risposta array per i client esistenti; i client
  aggiornati usano metadati e paginazione per completare la consultazione.
- Le vecchie sessioni amministrative interessate dalla nuova protezione possono
  richiedere un nuovo login. Reset e cambio email revocano i precedenti link pertinenti.
- Le fatture senza dati sufficienti conservano il nome già registrato oppure
  mostrano “Abbonamento”. Nessuna chiamata supplementare a Stripe per indovinarlo.
- Le tariffe AI restano stime interne, non importi garantiti della fattura del
  provider. I modelli non censiti producono un costo sconosciuto; il campo
  numerico storico conserva zero per compatibilità, con stato esplicito nei
  metadati. I totali del monitor segnalano le stime incomplete.
- I vecchi valori di costo non vengono convertiti o ricostruiti automaticamente.
  I documenti e i timestamp storici non vengono riscritti.
- Gli incassi reali restano disabilitati; i test usano servizi simulati e dati isolati.

## Limiti di rilascio ancora esterni a queste correzioni

- Occorre uno staging accessibile da dispositivi reali e una prova dei provider
  effettivamente configurati (OSRM, traffico, SMTP e archivio POD).
- Il restore automatico di prova del database non dimostra da solo il recupero
  coordinato del database e del bucket effettivi, né l'attivazione degli allarmi.
- Il limiter applicativo rimane per processo: un deploy distribuito richiede
  una politica condivisa al proxy o servizio equivalente.
- Le prove sintetiche non sostituiscono i giri reali anonimizzati, il pilota con
  aziende e le misure su 60–70 consegne al carico previsto.
- L'assegnazione globale multimezzo resta euristica; l'ottimo locale non è una
  prova di ottimalità dell'intera flotta o del traffico futuro.
- L'acquisto autonomo con pagamenti reali richiede un rilascio commerciale separato;
  non è stato attivato da questo intervento.

## File coinvolti

- **Accessi e permessi**: `app/core/dependencies.py`, `app/core/http_security.py`, `app/core/security.py`, `app/routers/admin_profile.py`, `app/routers/auth.py`, `app/services/sessions.py`, `tests/test_audit_security.py`, `tests/test_password_reset_identity.py`, `tests/test_rate_limit_sensitive.py`.
- **Giri, scheduler e provider**: `app/routers/driver.py`, `app/routers/operator.py`, `app/services/fleet_planning.py`, `app/services/optimizer_search.py`, `app/services/route_enrichment.py`, `app/services/route_execution.py`, `app/services/route_schedule.py`, `app/services/route_start.py`, `app/services/usage_limits.py`, `tests/test_delivery_tracking.py`, `tests/test_optimizer_scaling.py`, `tests/test_order_planning.py`, `tests/test_route_enrichment_concurrency.py`, `tests/test_route_execution_start.py`, `tests/test_route_execution_start_postgres.py`, `tests/test_route_schedule.py`, `tests/test_routing_architecture.py`.
- **Storico, interfacce e controlli UI**: `app/routers/routes.py`, `static/dashboard/index.html`, `static/dashboard/js/core.js`, `static/dashboard/js/history.js`, `static/design-system/components.css`, `static/driver/index.html`, `static/mobile/index.html`, `static/mobile/mobile.js`, `tests/check_v1_ui_regressions.py`, `tests/test_occasional_stops_ui.cjs`, `tests/test_route_history.py`, `tests/test_v1_ui_regressions.cjs`.
- **POD, fatture, prova e costi**: `app/routers/billing.py`, `app/services/ai_assistant.py`, `app/services/api_usage.py`, `app/services/billing.py`, `app/services/delivery_pod.py`, `static/landing/index.html`, `tests/test_api_costs.py`, `tests/test_billing.py`, `tests/test_delivery_pod.py`, `tests/test_electric_landing_ui.cjs`.

CI: `.github/workflows/tests.yml`, `tests/requirements-v1-audit.txt`.
Non sono necessarie nuove migrazioni del database o chiavi di produzione per
queste correzioni; la normale procedura di migrazione versionata resta invariata.
