# Percorso di pianificazione: confronto dei layout

Anteprime statiche con dati fittizi: non contattano l'applicazione, non salvano giri e non eseguono l'optimizer.
Le pagine reali restano invariate fino alla scelta richiesta da [CLAUDE.md](../CLAUDE.md).

## Problemi verificati sul codice attuale

1. Il percorso ora parte da Ordini/Clienti, ma alcune istruzioni chiedono ancora di configurare il giro prima di scegliere i clienti.
2. Il pulsante di avanzamento cambia significato tra completamento dati, modifica selezione e prosecuzione. Le consegne vengono nascoste finché non sono compilati tutti i campi.
3. Risorse, rientro e stime iniziali hanno peso visivo simile; alcune informazioni economiche si ripetono prima del risultato.
4. Peso e colli richiedono l'apertura dei dettagli di consegna, rendendo meno immediato il controllo del carico.
5. Nel risultato, azioni come stampa, navigazione, traffico e AI competono con la programmazione. Su mobile l'azione finale segue una lunga tabella.
6. Tornare alla selezione Clienti e proseguire ricrea il workspace: configurazione e modifiche alle consegne rischiano di essere azzerate. La migrazione dovrà preservarle per ID cliente/consegna.
7. Il flusso singolo e quello flotta usano etichette diverse per l'azione finale: uniformare a “Programma giro / giri”.

Riferimenti verificati: `static/dashboard/index.html`, `static/dashboard/js/core.js`, `customers.js`, `order-planning.js`, `fleet-planning.js`, `navigation.js`.

## Tre proposte

- **A — Percorso guidato** ([HTML](pianificazione-a.html)): un passaggio visibile alla volta. Si entra direttamente in Organizza con le consegne già scelte, poi si passa a Verifica e programma.
- **B — Pagina unica** ([HTML](pianificazione-b.html)): dati e consegne insieme, riepilogo laterale e risultato sotto il calcolo. Riduce i cambi di schermata nell'uso quotidiano.
- **C — Schede operative** ([HTML](pianificazione-c.html)): Configurazione, Fermate e Risultato in schede, con riepilogo condiviso. Tiene compatta la pagina, richiedendo però cambi di scheda.

Contenuti e stile sono gli stessi: cambiano disposizione e navigazione. Si riutilizzano esclusivamente `theme.css`, `components.css`, `layout.css`, shell e componenti esistenti; nessun CSS nuovo.
Fermate occasionali, doppie fasce, impostazioni complete della flotta, turni e pause rimangono funzionalità del prodotto; il demo non ne sostituisce gli editor esistenti.
Un giro con un mezzo è l'esempio iniziale. La modalità flotta resta visibile e selezionabile in tutte le varianti.

## Priorità comuni

- Selezione: numero di ordini/clienti e destinazioni, indirizzi da verificare, azione Vai alla pianificazione.
- Organizzazione: data/partenza/deposito, mezzo/autista, quantità e requisiti delle consegne; azione Calcola percorso.
- Opzioni espandibili: rientro, energia, raggruppamento, turni/pause e nome del giro.
- Risultato: risorse assegnate, stime e problemi da risolvere, azione Programma giro in alto prima della lista; altre azioni raccolte insieme.
- Programmazione: conferma e accesso ai giri programmati. L'anteprima mostra soltanto una simulazione.

Le stime sono illustrative: cambiarne i dati non avvia un calcolo reale. Le modifiche invalidano comunque il risultato di prova per rendere comprensibile il flusso.

## Come aprire le anteprime

Nel checkout aprire uno dei tre file HTML in questa cartella, mantenendo la directory `../static/design-system/`.
In alternativa scaricare l'artifact **planning-layout-previews** dall'esecuzione GitHub Actions, estrarlo interamente e aprire `anteprime/pianificazione-a.html`.
L'artifact contiene anche gli screenshot a 390, 768, 1024 e 1440 px e il report dei controlli.

## Verifica

```sh
pip install playwright==1.55.0
python -m playwright install chromium
python tests/check_planning_previews.py
```

Il test usa un server HTTP locale, senza importare Flask o collegarsi al database.
Controlla tutte le varianti ai quattro viewport, overflow, errori JavaScript, persistenza dei campi/quantità, cambio selezione, invalidazione del risultato, input negativi, flotta e simulazione di programmazione.
Ogni tentativo di chiamare API o servizi esterni fa fallire il controllo; i font remoti vengono sostituiti localmente.

## Migrazione dopo la scelta

1. Applicare il layout scelto ai gestori esistenti di configurazione e calcolo; conservare permessi e controlli.
2. Correggere il ritorno alla selezione preservando la bozza e i dettagli delle consegne per ID; conservare riferimenti agli ordini e versioni.
3. Disporre il risultato singolo/flotta con la stessa gerarchia, mantenendo vincoli, ricalcolo manuale, assegnazioni e gestione fermate non assegnate.
4. Eseguire regressioni backend/JavaScript/browser sui dati reali di test e ai quattro viewport; eliminare queste anteprime dopo l'applicazione.

Non sono previste modifiche a database, API, optimizer, prezzi o permessi.
