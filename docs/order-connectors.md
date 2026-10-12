# Ricezione automatica degli ordini aziendali

Ogni azienda configura fonti separate da Ordini > Collega i tuoi ordini. Nessuna lettura delle email personali del gestore GiroFacile. I nuovi ordini ricevuti rimangono autonomi dai Clienti e richiedono la verifica dell'indirizzo prima della pianificazione. Non vengono avviati giri automaticamente.

## Funzioni implementate

- Shopify: ricezione firmata degli eventi `orders/create`, indirizzo di spedizione e articoli.
- WooCommerce: ricezione firmata degli eventi `order.created`, indirizzo di spedizione e articoli. Dominio HTTPS alla radice (installazioni in sottocartelle non incluse).
- Email: indirizzo Postmark con suffisso casuale distinto per azienda/fonte; inoltro dalla casella aziendale. Importa allegati CSV/Excel con colonne riconosciute oppure testo con righe etichettate. Non serve concedere accesso alla casella completa.
- Preferenze dei campi applicate dal motore di acquisizione; data consegna esclusa inizialmente. Numero ordine, destinatario e indirizzo richiesti.
- Firma HMAC sul corpo originale per i negozi, Basic Authentication sul canale Postmark, controllo negozio/destinatario, limiti di dimensione e frequenza, isolamento aziendale, transazioni e deduplicazione.
- Chiavi dei negozi cifrate con Fernet, mai restituite al browser. Configurazione riservata al titolare; permessi esistenti per preferenze, pausa e rimozione.
- Stato di attesa fino al primo messaggio autenticato; esito reale disponibile nello storico. Una connessione predisposta non certifica che il negozio o la regola di inoltro siano stati configurati.

## Attivazione infrastruttura GiroFacile (una volta per installazione)

Installare le dipendenze aggiornate da requirements.txt, inclusa cryptography. Nessuna migrazione SQL aggiuntiva.

1. Configurare `APP_BASE_URL` con l'URL pubblico HTTPS dell'installazione.
2. Generare e custodire nel gestore segreti `ORDER_CONNECTOR_KEY`, una chiave Fernet generata con `Fernet.generate_key()`. Deve rimanere stabile e inclusa nei backup sicuri; sostituirla senza ricifrare le configurazioni rende inutilizzabili le chiavi esistenti. Non usare APP_SECRET come ripiego.
3. Per le email predisporre un server/stream inbound Postmark. Impostare `ORDER_INBOUND_ADDRESS` con l'indirizzo assegnato, ad esempio `hash@inbound.postmarkapp.com`, e `ORDER_INBOUND_PASSWORD` casuale di almeno 32 caratteri.
4. Configurare il webhook inbound di Postmark su `/api/order-connectors/email` con autenticazione Basic: username `girofacile` e password configurata. Se si inseriscono credenziali nell'URL Postmark, codificarle correttamente e non riportare tale URL nei log o nelle schermate. Configurare il limite/spam filter Postmark e il rate limiter del proxy.
5. In assenza delle impostazioni richieste, la creazione della relativa fonte restituisce una spiegazione e non simula un collegamento attivo. La configurazione del provider esterno non viene effettuata dal codice e non e stata attivata da questo intervento.

## Configurazione per azienda

Email: il titolare crea la fonte, copia l'indirizzo dedicato e imposta l'inoltro delle sole email d'ordine. L'indirizzo casuale e una destinazione riservata, non autentica il cliente mittente: chi lo conosce puo inviare messaggi. Controllare sempre gli ordini ricevuti. Per un testo strutturato:

```
Numero ordine: EMAIL-2026-001
Destinatario: Mario Rossi
Indirizzo: Via Roma 1, 00100 Roma
Colli: 3
Note: Citofonare Rossi
```

CSV/Excel usano gli stessi alias dell'importazione file. Colonne ambigue o dati mancanti producono un errore nello storico, senza import parziale. Limite 2 MB per l'intero webhook JSON (allegati base64 inclusi), 1000 ordini, 10 allegati. Le email senza formato riconoscibile e gli allegati PDF/immagini richiedono lettura dell'originale e inserimento manuale: non esiste ancora estrazione AI/OCR del testo libero. Il corpo email non viene conservato nel database; i dati estratti seguono la conservazione ordini esistente.

Shopify: inserire dominio originale `negozio.myshopify.com` e chiave di firma dei webhook; creare nelle Notifiche un webhook Ordine creato, JSON, diretto all'URL mostrato. WooCommerce: stesso percorso guidato, webhook Ordine creato e stessa chiave inserita in GiroFacile. Il ping iniziale WooCommerce non autenticato verifica soltanto la raggiungibilita e non crea ordini o marca il collegamento come verificato.

Inviare un ordine reale di prova, controllare lo storico e il destinatario. Non e un'app OAuth da installare con un clic: serve questa configurazione iniziale nel negozio. Altre piattaforme possono usare l'API standard; non viene dichiarata compatibilita universale.

## Limiti e gestione operativa

Questa versione riceve i NUOVI ordini. Non sincronizza lo storico, aggiornamenti, annullamenti, rimborsi o stato di consegna verso il negozio. Non interpreta quantita degli articoli come colli e non sostituisce indirizzi di spedizione con indirizzi di fatturazione. Ordini privi di indirizzo o annullati sono segnalati. Gli invii autenticati con errori di contenuto vengono registrati e confermati al provider per evitare retry infiniti; correggere nella fonte e inviare un nuovo evento/email. Non ripetere lo stesso identificativo con un corpo diverso. Consultare lo storico per gli errori.

Pausa blocca la ricezione con errore temporaneo: i retry sono governati dal provider e non sono illimitati. Prima di pause prolungate, fermare anche l'inoltro/webhook nel servizio esterno. La rimozione conserva gli ordini ma elimina il collegamento. Per cambiare la chiave di firma fermare il webhook e riconfigurare il collegamento; non reinviare lo storico su una nuova fonte per evitare duplicati tra fonti diverse.

## Riferimenti verificati

- Shopify, verifica delle firme: https://shopify.dev/docs/apps/build/webhooks/verify-deliveries
- Shopify, configurazione manuale: https://help.shopify.com/en/manual/fulfillment/setup/notifications/webhooks
- WooCommerce, webhook: https://woocommerce.com/document/webhooks/
- Postmark, ricezione: https://postmarkapp.com/developer/webhooks/inbound-webhook
- Postmark, autenticazione: https://postmarkapp.com/developer/webhooks/webhooks-overview

La verifica automatizzata usa database isolati e payload firmati locali. Nessun account aziendale esterno viene contattato e nessun messaggio viene inviato. La verifica end-to-end con negozio e posta reali rimane necessaria dopo l'attivazione infrastrutturale.

## Esiti dei controlli locali

37 test Python su connettori, acquisizione, permessi e pianificazione superati; 9 test connettori rieseguiti dopo gli ultimi affinamenti. Browser dedicato a configurazione email/Shopify e preferenze verificato a 390/768/1024/1440 pixel. I controlli statici frontend conservano tre fallimenti gia noti su KPI carburante, password e vecchia descrizione onboarding API. Il test browser generale ordini si interrompe sul click della selezione multipla nella vista mobile, prima della configurazione connettori; la relativa interfaccia non e stata modificata in questo intervento.
