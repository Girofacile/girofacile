# Piani e abbonamenti: rilascio sandbox

| Piano | EUR/mese | Clienti | Mezzi / autisti | Depositi | Giri/mese | Consegne/mese |
|---|---:|---:|---:|---:|---:|---:|
| Starter | 29 | 150 | 3 / 3 | 1 | 100 | 2.000 |
| Business | 59 | 500 | 10 / 10 | 3 | 400 | 10.000 |
| Pro | 99 | 5.000 | 50 / 50 | 20 | 1.500 | 30.000 |

Listino unico in `app/services/plan_catalog.py`. Nessuna promozione iniziale.
AI solo Pro, senza quota mensile. Chat, agenti e report da Business.
Esportazione dei propri dati inclusa in tutti i piani, anche dopo la scadenza.
La presentazione fiscale e lo SDI non sono attivati da questa integrazione.

## Garanzie di questa versione

- `BILLING_MODE=disabled` è il default; `test` usa la sandbox, `live` i pagamenti reali (sezione dedicata sotto).
- Solo chiavi `sk_test_` / `rk_test_` e oggetti Stripe con `livemode=false`.
- Checkout e portale solo per gli ID elencati in `BILLING_TEST_USER_IDS`.
- Non riutilizzare un account aziendale reale per il collaudo.
- Prova di 14 giorni senza carta; acquisto esplicito. Nessun rinnovo del trial
  tramite cambio piano. Le date dei trial esistenti rimangono invariate.
- Upgrade: preventivo, conguaglio e applicazione solo dopo il pagamento.
- Downgrade al rinnovo, preceduto dal controllo delle risorse registrate.
- Disdetta a fine periodo; possibilità di ripristinare il rinnovo.
- Tolleranza di 7 giorni per rinnovi falliti di account precedentemente paganti.
- I webhook rileggono lo stato corrente Stripe e registrano gli eventi elaborati.
- Nessun documento di prova viene contato negli incassi reali.

## Pagamenti reali (`BILLING_MODE=live`)

- Acquisti aperti a tutte le aziende; `BILLING_TEST_USER_IDS` non serve.
- Solo chiavi `sk_live_` / `rk_live_` e oggetti Stripe con `livemode=true`: un evento o un prezzo della sandbox viene rifiutato.
- Gli account con origine `stripe_live` sono i paganti (MRR); quelli `stripe_test` restano fuori e, se acquistano,
  ricevono un nuovo cliente Stripe reale (il cliente sandbox non esiste nell'account reale).
- Il checkout raccoglie indirizzo di fatturazione e partita IVA sul cliente Stripe.
- Il prezzo addebitato è quello del listino (2900, 5900, 9900 centesimi al mese), senza imposte aggiunte da Stripe.
- La fattura elettronica (SDI) non è emessa da GiroFacile: va emessa a parte finché non si collega un servizio dedicato.
- All'avvio il server non parte se manca uno di questi valori o se la chiave è di un'altra modalità:

```
BILLING_MODE=live
STRIPE_SECRET_KEY=<chiave segreta reale o chiave limitata rk_live_>
STRIPE_WEBHOOK_SECRET=<segreto dell'endpoint reale>
STRIPE_PRICE_STARTER=<price reale Starter>
STRIPE_PRICE_BUSINESS=<price reale Business>
STRIPE_PRICE_PRO=<price reale Pro>
```

Nell'account reale vanno creati di nuovo prodotti, prezzi ed endpoint webhook (`https://girofacile.it/api/billing/webhook`,
stessi eventi della sandbox): quelli della sandbox non vengono copiati.

## Configurazione di collaudo (solo sul server di test)

Creare tre prezzi ricorrenti mensili EUR nella sandbox Stripe, rispettivamente
2900, 5900 e 9900 centesimi. La validazione server rifiuta prezzi diversi.
Configurare nell'ambiente, mai in Git:

```
BILLING_MODE=test
BILLING_TEST_USER_IDS=123
STRIPE_SECRET_KEY=<chiave sandbox>
STRIPE_WEBHOOK_SECRET=<segreto endpoint sandbox>
STRIPE_PRICE_STARTER=<price sandbox Starter>
STRIPE_PRICE_BUSINESS=<price sandbox Business>
STRIPE_PRICE_PRO=<price sandbox Pro>
APP_BASE_URL=https://<host di test>
```

Registrare `/api/billing/webhook` per `checkout.session.completed`,
`customer.subscription.created/updated/deleted`, `invoice.paid`,
`invoice.payment_failed`, `invoice.payment_action_required`.
Versione API fissata a `2025-06-30.basil`, senza API preview.
Il portale creato dall'app consente metodi di pagamento e documenti; i cambi
piano passano dall'app per rispettare limiti, conguagli e decorrenze.

## Quote e dati esistenti

Le quote usano il mese di calendario Europe/Rome. Una bozza non consuma giri.
Il primo avvio registra il numero di fermate; cancellazioni e cancellazione del
giro non restituiscono quota. I giri iniziati non possono essere riscritti.
I giri già in corso prima dell'aggiornamento restano completabili.
I limiti sulle risorse contano i record non archiviati; la disattivazione di una
credenziale autista non libera un posto nell'anagrafica.
Un downgrade successivamente sopra soglia non elimina dati: limita nuove creazioni.

La migrazione aggiunge colonne e tabelle senza cambiare piani o date esistenti.
Gli account storici senza origine billing sono mostrati come amministrativi,
esclusi dall'MRR pagante. Le assegnazioni manuali vengono registrate nell'attività.
Non eseguire migrazioni o test sui dump di produzione per il collaudo.

## Promemoria e operatività

`python scripts/billing_reminders.py` mostra soltanto i conteggi.
Con `--send` invia promemoria di fine prova (entro 3 giorni e alla scadenza),
pagamento fallito e disdetta. Sul server lo avvia ogni giorno alle 9:00 `deploy/systemd/girofacile-reminders.timer`.
Gli avvisi di fine prova partono solo per prove scadute da non più di 7 giorni; aziende sospese e
amministratore non ricevono avvisi. In modalità live il testo invita ad acquistare dalla pagina Piani. Ogni avviso riuscito è registrato per evitare ripetizioni;
un crash fra invio SMTP e commit può causare una ripetizione al successivo tentativo.
Coordinare con le email Stripe per evitare avvisi equivalenti duplicati.

Il pulsante Aggiorna stato e `/api/admin/users/{id}/billing-sync` permettono
il recupero manuale dei webhook mancanti. Monitorare risposte non 2xx del webhook
e consentire a Stripe i retry. Non attivare gli incassi reali senza un rilascio
successivo, verifica fiscale e collaudo end-to-end della sandbox.
