# Piani GiroFacile

Il catalogo condiviso da server, dashboard, sito e amministrazione è
`app/services/plan_catalog.py`. Gli importi mensili sono IVA esclusa.

| Risorsa | Starter | Business | Pro |
| --- | ---: | ---: | ---: |
| Prezzo mensile | €29 | €59 | €99 |
| Ordini acquisiti al mese | 300 | 1.200 | 6.000 |
| Clienti registrati | 150 | 500 | 5.000 |
| Depositi | 1 | 3 | 20 |
| Autisti | 3 | 10 | 50 |
| Mezzi standard | 3 | 10 | 50 |
| Mezzi elettrici aggiuntivi | +1 | +2 | +5 |
| Collaboratori aziendali | 2 | 5 | 10 |

Tutti i piani includono inserimento manuale e importazione CSV/Excel degli
ordini, pianificazione su un mezzo, portale autista, GPS autista interno,
esiti e note, storico ed esportazione dati di base.

Business e Pro includono tracking clienti, suddivisione automatica su più mezzi,
chat autisti, agenti e relativo portale, report avanzati ed esportazione report,
firma, foto e PDF di consegna, integrazioni API, Shopify e WooCommerce.
**Integrazione AI** è inclusa solo in Pro. L'inoltro email rimane in sviluppo.

## Utilizzo delle quote

La quota ordini si rinnova a inizio mese nel fuso `Europe/Rome` e si applica
agli ordini nuovi inseriti manualmente o acquisiti dalle fonti di importazione.
Aggiornamenti e reinvii riconosciuti come duplicati non consumano altri ordini.
Un'importazione che supera il residuo viene respinta interamente. Anteprime e
importazioni fallite non consumano la quota; annullamento o eliminazione di un
ordine acquisito non restituiscono il credito. Non esiste un limite commerciale
mensile separato per giri, ricalcoli o consegne.

I posti collaboratore escludono il titolare e comprendono gli account attivi
con invito ancora in attesa. Disattivare un account libera il posto; riattivarlo
richiede un posto disponibile.

Un downgrade conserva dati, documenti e preferenze. Le nuove aggiunte sono
bloccate quando superano la rispettiva quota. Le funzioni premium escluse
sono disabilitate anche sul server: i link pubblici di tracking e i connettori
esistenti non aggirano il piano corrente. Preferenze storiche di firma o foto
non impediscono di completare una consegna con Starter.

## Aggiornamento

La migrazione `20261023_01` aggiunge il contatore persistente degli ordini mensili
e lo inizializza dagli ordini già presenti, senza modificarli. Eseguire
`python -m app.migrations` prima di avviare i worker; gli script di avvio
e l'immagine Docker lo fanno già. Non applicare migrazioni con worker della
versione precedente ancora attivi.

Questa modifica non abilita incassi reali né modifica i prezzi configurati
nel pannello Stripe: le protezioni di fatturazione esistenti restano attive.
