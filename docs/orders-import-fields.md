# Dati da importare per fonte

Il passaggio Controlla dati dei file e la pagina del collegamento API mostrano le preferenze per i campi da acquisire. Nome destinatario e indirizzo sono essenziali; numero e identificativo restano necessari per gli aggiornamenti senza duplicati. Data, fascia oraria, colli, peso, attrezzature, note, articoli e codice cliente sono selezionabili. La fascia oraria viene esclusa come coppia.

Le preferenze si salvano nella configurazione JSON esistente: nessuna migrazione database. I campi esclusi vengono ignorati prima della validazione, anche se arrivano tramite alias API. Cambiare le preferenze invalida le anteprime precedenti, senza sospendere la fonte o revocare la chiave. Solo il permesso orders.integrations consente di cambiarle.

Le fonti preesistenti continuano a ricevere dati come prima fino al salvataggio delle preferenze. Il nuovo percorso UI salva queste preferenze e richiede destinatario e indirizzo. Non cambiano gli ordini esistenti automaticamente: un successivo import aggiorna i dati ricevuti, preservando originale e correzioni manuali. Per le API serve un nuovo batch_id per un nuovo invio; ritentare lo stesso batch rimane idempotente.

Verifiche: test acquisizione file/API, preferenze persistenti, esclusione di valori invalidi, ripristino della validazione, controllo permessi e versioni, reimport con rimozione della data, originale preservato. Browser con API reale su database isolato a 390/768/1024/1440 pixel, selezione campi file e salvataggio API.

Esito: 27 test Python superati. I controlli statici frontend segnalano i tre errori preesistenti su KPI carburante, cambio password e vecchio testo onboarding API; non modificati da questo intervento.
