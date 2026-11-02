# Pianificazione multi mezzo con solutore specializzato

Rapporto della versione `8bdcd61`: comprendeva la precedente sponda bloccante.
La politica attuale è descritta in [Pianificazione su più mezzi](fleet-planning.md):
la sponda è un avviso e non esclude consegne né blocca la programmazione.

Questo confronto parte dalla versione pubblicata `dbe4641`, che aveva tredici
esecuzioni con consegne fattibili escluse su 124 combinazioni di dati, strategia
e ordine degli input. La copertura è verificata prima di valutare i risparmi.

## Ricerca e modello matematico

La ricerca adattiva precedente resta il primo candidato. Quando esclude una
fermata che potrebbe essere servita da almeno una risorsa, una seconda ricerca
completa esplora la strategia complementare sulla stessa matrice e sulle
costruzioni iniziali già disponibili. L'accettazione segue sempre la strategia
scelta dall'operatore: prima copertura e compatibilità, poi chilometri/tempi o
bilanciamento. L'altra strategia serve a trovare una diversa assegnazione
fattibile, senza cambiare la priorità dichiarata all'utente.

Se la copertura resta incompleta, una riparazione coordinata prova uno scambio
fra due mezzi e l'inserimento di una consegna mancante. Conserva gli altri
ordini relativi, ma verifica tutte le posizioni dei tre movimenti. I controlli
di peso, colli e sponda precedono il calendario preparato, che riusa la stessa
aritmetica di pause e finestre del valutatore canonico. Ogni miglioramento viene
confermato dal calendario completo; il procedimento può recuperare più fermate
in successione entro un massimo di tre secondi.

Quando occorre una riorganizzazione ulteriore, un modello misto intero viene risolto da
**HiGHS tramite SciPy**, già disponibile nell'ambiente e fissato nelle
dipendenze. Il modello decide insieme assegnazioni ai mezzi e collegamenti fra
fermate: capacità in kg/colli, sponda richiesta, finestre di scarico, turni,
pause, rientro e orizzonte disponibile sono vincoli della stessa ricerca.
Le variabili di ordine impediscono anche circuiti scollegati a durata zero.

Per ogni autista, il calendario di lavoro elimina dalla linea del tempo le
pause fisse: la guida può interrompersi e riprendere, mentre i domini di inizio
servizio impediscono di spezzare lo scarico. Ogni itinerario proposto viene poi
rivalutato dal calendario canonico dell'applicazione. Un candidato che non
supera tale verifica viene scartato.

L'obiettivo interno del modello favorisce un recupero fattibile vicino ai giri
già trovati. L'accettazione finale usa l'obiettivo effettivo della flotta; una
soluzione del modello non viene presentata come prova del minimo globale dei
chilometri. Un limite di tempo o l'assenza di un candidato valido non dimostrano
che una consegna sia fisicamente impossibile.

Il piano parziale già valido fornisce anche suggerimenti di avvio al solutore:
restano suggeriti gli abbinamenti e i collegamenti esterni a un vicinato delle
consegne mancanti. HiGHS può modificarli durante la ricerca globale. Nessun
itinerario testimone del benchmark entra in questi suggerimenti. L'accesso
all'interfaccia nativa inclusa in SciPy è isolato in un adattatore, con versione
fissata, verifica del risultato intero e ripiego sull'interfaccia pubblica se
quella nativa non è disponibile. Il controllo canonico degli itinerari resta
obbligatorio anche quando HiGHS riporta un risultato ammissibile.

Il recupero ha un limite separato di 30 secondi, comprendente la ricerca
complementare e il tempo rimanente per il modello matematico. La ricerca
complementare espone il proprio numero di valutazioni e il proprio budget nella
diagnostica. Tutte le fasi riusano la matrice stradale condivisa: nessuna nuova
richiesta API per combinazione e nessuna quota a pagamento del solutore locale.

## Criterio di verifica

La campagna precedente contiene 31 problemi da cinquanta consegne e flotte da
due a cinque mezzi. Si conservano gli stessi input e le stesse matrici stradali,
con entrambe le strategie e ordine originale/inverso. Dodici problemi aggiuntivi
usano semi mai impiegati nelle due precedenti campagne, fissati nel file
`tests/fleet_constraint_holdout.py` prima di esaminare le risposte del solutore.
Durante questa qualificazione, problemi a due e quattro mezzi hanno evidenziato
ulteriori esclusioni. Quei controesempi hanno guidato l'aggiunta della riparazione
coordinata generica e dei suggerimenti di avvio; i dodici problemi sono quindi una suite aggiuntiva di
qualificazione e regressione, non un campione cieco successivo all'ultima
modifica. I semi e le finestre non sono stati cambiati.

Ogni problema contiene un piano testimone costruito senza il motore in esame e
verificato da un calendario indipendente. Le assegnazioni e gli ordini del
testimone non vengono forniti al solutore. Il calendario verifica capacità in
kg e colli, sponda, finestre, scarico, pause fisse, turno, disponibilità, rientro
ed energia del singolo mezzo. Autonomia e ricariche non sono modellate perché
il modello attuale dei mezzi non contiene questi dati.

La baseline comprende i cinque moduli pubblicati di distribuzione e ricerca.
Le risposte della campagna precedente vengono riusate soltanto se gli hash
dei sorgenti e tutti gli input coincidono con tale revisione. Quando gli
artifact non sono disponibili, il runner carica i sorgenti dalla cronologia Git
ed esegue nuovamente la baseline. Il motore del giro singolo e il calendario
comuni devono rimanere invariati, altrimenti il confronto si interrompe.

Si confrontano chilometri e minuti direttamente soltanto quando entrambi i
piani sono validi, servono esattamente le stesse consegne e hanno il medesimo
numero di incompatibilità ZTL. Servire più fermate non viene presentato come
un risparmio a parità di servizio.

```sh
python tests/run_fleet_constraint_benchmark.py --split prior --only-gaps --strict
python tests/run_fleet_constraint_benchmark.py --split prior --strict
python tests/run_fleet_constraint_benchmark.py --split fresh --strict
python tests/run_fleet_constraint_benchmark.py --strict
```

Il comando rigoroso richiede la copertura dimostrata per ogni input selezionato,
assenza di violazioni operative, assenza di regressioni dell'obiettivo rispetto
alla baseline valida e sorgenti invariati durante la misura. Input, matrici,
risposte complete, confronti, metadati e copie esatte dei sorgenti misurati sono conservati in
`test-results/fleet-constraint/comparison/`. Non vengono chiamati provider reali.

Un piano che serve tutte le consegne del testimone dimostra la copertura di quel
problema; non certifica il minimo globale dei chilometri né il traffico futuro.
I tempi misurati senza database e provider non costituiscono uno SLA.

## Risultati misurati

La campagna mirata alle tredici precedenti esclusioni è stata eseguita sul
motore integrato e congelato, con hash iniziali e finali coincidenti:

- **13/13 esecuzioni** raggiungono cinquanta consegne: **650/650**, rispetto alle
  precedenti 633. Sono recuperate tutte le diciassette esclusioni osservate.
- Nove esecuzioni recuperano la copertura con la ricerca complementare; le
  quattro rimanenti richiedono il modello globale HiGHS e raggiungono anch'esse
  cinquanta consegne, con entrambe le strategie e i due ordini degli input.
- Nessuna violazione del calendario indipendente, duplicazione, discordanza
  energetica o richiesta a provider esterni. Nessuna regressione dell'obiettivo.
- Il confronto rigoroso termina con codice zero. I piani testimone non sono
  stati forniti al motore.

Nel controllo mirato il tempo mediano del nucleo è 8,48 secondi, il massimo
16,74 secondi. Il modello globale richiede circa 9,55–10,06 secondi nei quattro
casi in cui interviene. Sono tempi offline di questo ambiente, senza database e
provider; non rappresentano uno SLA del servizio in produzione.

## Qualificazione finale del 1 novembre 2026

Completate entrambe le campagne sulla versione finale, con tutti i 19 hash dei
sorgenti e delle dipendenze invariati dall'inizio alla fine:

| Campagna | Problemi | Esecuzioni | Copertura dimostrata raggiunta | Consegne recuperate |
| --- | ---: | ---: | ---: | ---: |
| Precedenti | 31 | 124 | 124/124 | 17 |
| Aggiuntivi | 12 | 48 | 48/48 | 20 |
| Totale | 43 | 172 | 172/172 | 37 |

Nei 172 piani finali: **zero consegne fattibili escluse**, zero violazioni,
duplicazioni, errori energetici, chiamate esterne o regressioni dell'obiettivo.
Sono servite **8.592 consegne sulle 8.592 dimostrate fattibili**, rispetto alle
precedenti 8.555. Otto esecuzioni dei controlli negativi servono correttamente
49 consegne: una fermata supera la capacità di ogni mezzo oppure richiede una
sponda assente su tutta la flotta. Le altre 164 servono cinquanta consegne.

Le due campagne complete hanno superato il controllo rigoroso. Il rapporto
aggregato con input, risposte complete e copie esatte dei sorgenti è in
`test-results/fleet-constraint/comparison/`. I sorgenti principali misurati sono:

- Modello e riparazione: SHA256
  `36e4cc8fbdac99c4dff0dfb00da05343ccffc1945b5b6665b853cdac7fccac49`.
- Adattatore HiGHS: SHA256
  `6731a6cad0b7d1229e70aa298b83e5c5f6c8c505df3d7011c375dc2a3f7024ce`.

Questo aggiornamento migliora soprattutto la copertura. A parità delle stesse
consegne già servite, mantiene i chilometri e i tempi della versione `dbe4641`;
non attribuisce a questo secondo intervento i risparmi misurati nel precedente
aggiornamento. La copertura completa del campione non certifica il minimo globale
dei chilometri né garantisce una soluzione completa su ogni input futuro.

La CI ora richiede la copertura dimostrata: è stata rimossa l'eccezione che
tollerava le tredici esclusioni precedenti. Giro singolo e calendario canonico
restano invariati; non servono nuove chiavi API o migrazioni.

La suite integrata di flotta, turni, API e riferimenti indipendenti supera
**271 test**, con un fallimento atteso già documentato sul prezzo energetico
manuale pari a zero. I 128 controlli mirati del motore superano anch'essi la
verifica. L'allineamento ai successivi aggiornamenti dell'interfaccia su `main`
non modifica nessuno dei 19 sorgenti misurati nelle campagne complete.
