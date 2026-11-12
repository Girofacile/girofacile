# Widget GiroFacile su iPhone

Il widget usa l’app Scriptable e legge gli indicatori della piattaforma con la
chiave dedicata creata nel pannello Super Admin, in **Server → Widget iPhone**.

![Anteprima del widget chiaro GiroFacile](assets/widget-iphone-light.png)

Anteprima grafica ricostruita dai comandi dello script, con dati di esempio.
La resa dei font e delle icone va verificata in Scriptable su iPhone.

## Aspetto e formati

Il tema chiaro usa il blu GiroFacile, riquadri arrotondati e numeri con contrasto
e dimensioni maggiori per gli indicatori principali.

- **Grande:** ticket aperti e nuovi di oggi, aziende registrate, in prova,
  abbonate e nuove nel mese, giri di oggi e in corso, errori delle ultime 24 ore
  e MRR stimato. Le due schede principali precedono due righe di indicatori e
  una fascia per il MRR, senza concentrare tutto nella parte alta.
- **Medio:** ticket aperti, ticket di oggi, aziende registrate, aziende in prova,
  abbonate e giri in corso.
- **Piccolo:** ticket aperti e aziende registrate.

Gli zeri sono conteggi reali; un valore mancante è rappresentato da un trattino.
Gli errori delle ultime 24 ore assumono un colore di attenzione solo quando
sono maggiori di zero. Il widget mostra l’orario dei dati ricevuti; dopo 30
minuti segnala che si tratta di dati precedenti. In assenza di connessione mostra uno stato
di indisponibilità, senza inventare conteggi.

## Aggiornare un widget già installato

Una modifica sul server non sostituisce automaticamente lo script salvato
nell’app Scriptable. Dopo aver aggiornato GiroFacile sul server:

1. Aprire **Super Admin → Server → Widget iPhone**.
2. Premere **Genera chiave e copia script**. L’operazione sostituisce la chiave:
   eventuali altre copie dello script precedente dovranno essere aggiornate.
3. Su iPhone aprire lo script “GiroFacile” in Scriptable, sostituire il contenuto
   con quello appena copiato, salvare e avviarlo una volta per vedere l’anteprima.
4. Il widget già presente nella Home continua a usare lo stesso script. Se
   necessario, verificarne il nome tenendo premuto il widget e scegliendo
   **Modifica widget**.

In alternativa si può usare il nuovo file
[`static/admin/widget-scriptable.js`](../static/admin/widget-scriptable.js),
riportando nelle due costanti `GF_URL` e `GF_KEY` i valori del proprio script
già installato. Questo mantiene la chiave esistente. Lo script configurato
contiene una credenziale di lettura: non pubblicarlo e non inviarlo in chat.

Un tocco sul widget apre il pannello Admin. Lo script richiede un aggiornamento
dopo 15 minuti, ma la frequenza effettiva è decisa da iOS.

## Verifica del layout

I test JavaScript eseguono lo script con le API Scriptable simulate e verificano
i tre formati, i conteggi, gli errori e il collegamento al servizio. Le anteprime
grafiche ricostruite nel browser aiutano a controllare gli ingombri, ma non
sostituiscono la prova su iPhone: font, simboli e spaziatura possono variare nella
resa nativa di Scriptable e con le impostazioni della Home di iOS.
