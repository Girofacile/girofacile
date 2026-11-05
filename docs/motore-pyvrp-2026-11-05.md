# Motore dei giri con PyVRP — misure del 5 novembre 2026

Con «Riduci chilometri e tempi» e più mezzi, il piano trovato dalla ricerca di GiroFacile
viene ora confrontato con due proposte esterne: OR-Tools (già presente) e **PyVRP 0.14.1**
(libreria gratuita, licenza MIT, eseguita sul server, nessuna chiamata esterna). Nessuna
proposta viene presa così com'è: ogni giro passa dal calendario canonico (pause, fasce,
turni, capacità, sponda, ZTL, punteggio km + ore) e vince il piano migliore secondo la
strategia, prima per consegne servite e poi per punteggio. Codice: `app/services/fleet_pyvrp.py`.

## Come si è misurato

- **Problemi pubblici di Solomon** (36 istanze da 100 consegne con fasce orarie, capacità e
  numero di mezzi fisso), confrontati con le migliori soluzioni note pubblicate da SINTEF.
  Ogni piano è ricontrollato da un verificatore indipendente che non usa codice dell'app e
  che riproduce esattamente i km delle migliori soluzioni note. Un piano che lascia fuori
  anche una sola consegna è «non valido». Scarto = km in più rispetto alla migliore nota.
- **Piani reali** salvati nel database locale, rigiocati offline con il codice nuovo e
  confrontati con lo stesso codice senza PyVRP. I piani migliorati sono stati ricontrollati
  con il verificatore indipendente (`tests/routing_quality_oracle.py`).

## Risultati su Solomon

| Configurazione | Piani validi | Consegne escluse | Scarto medio | Scarto massimo | Uguali alla migliore nota |
|---|---:|---:|---:|---:|---:|
| Motore precedente (ricerca + OR-Tools 10 s) | 22/36 | 70 | 14,9%¹ | 43,2%¹ | 2 |
| PyVRP da solo, 30 s | 34/36 | 2 | 0,42%¹ | 2,3%¹ | 13 |
| **GiroFacile + OR-Tools + PyVRP** | **36/36** | **0** | **0,71%** | **3,8%** | **14** |

¹ Sui 22 problemi validi per tutti; sugli stessi 22 la combinazione ha scarto medio 0,41%.
Mediana della combinazione su tutti i 36: 0,40%. Tempo medio di calcolo con 100 consegne
circa 105 s (PyVRP al massimo 30 s, OR-Tools 10 s, il resto è la ricerca già esistente).

**Lettura.** Su problemi di riferimento difficili la combinazione serve sempre tutte le
consegne e resta in media a meno dell'1% dalla migliore soluzione mai trovata (ottenute
dalla ricerca con ore di calcolo); il caso peggiore è r112 al 3,8%. Il motore precedente
in 14 problemi su 36 lasciava fuori consegne servibili.

### Dettaglio per problema

| Problema | Mezzi | Km migliori noti | Motore attuale | PyVRP da solo | GiroFacile + PyVRP |
|---|---:|---:|---:|---:|---:|
| c101 | 10 | 828,94 | 0,00% | 0,00% | 0,00% |
| c102 | 10 | 828,94 | +21,41% | 0,00% | 0,00% |
| c103 | 10 | 828,06 | +43,23% | 0,00% | 0,00% |
| c104 | 10 | 824,78 | +19,61% | 0,00% | 0,00% |
| c105 | 10 | 828,94 | +3,06% | 0,00% | 0,00% |
| c106 | 10 | 828,94 | 0,00% | 0,00% | 0,00% |
| c107 | 10 | 828,94 | +8,93% | 0,00% | 0,00% |
| c108 | 10 | 828,94 | +10,31% | 0,00% | 0,00% |
| c109 | 10 | 828,94 | +29,73% | 0,00% | 0,00% |
| r104 | 9 | 1007,31 | non valido (7 escluse) | 0,00% | +1,08% |
| r107 | 10 | 1104,66 | non valido (3 escluse) | +1,32% | +0,92% |
| r108 | 9 | 960,88 | non valido (7 escluse) | +1,37% | +0,67% |
| r110 | 10 | 1118,84 | non valido (7 escluse) | non valido (1 escluse) | +1,95% |
| r111 | 10 | 1096,73 | non valido (7 escluse) | +2,06% | +0,91% |
| r112 | 9 | 982,14 | non valido (7 escluse) | non valido (1 escluse) | +3,83% |
| rc104 | 10 | 1135,48 | non valido (2 escluse) | 0,00% | 0,00% |
| rc108 | 10 | 1139,82 | non valido (5 escluse) | 0,00% | 0,00% |
| r201 | 4 | 1252,37 | +6,33% | 0,00% | 0,00% |
| r202 | 3 | 1191,7 | non valido (2 escluse) | +1,96% | +0,47% |
| r203 | 3 | 939,5 | +19,39% | +0,33% | +0,20% |
| r204 | 2 | 825,52 | non valido (5 escluse) | +3,71% | +1,21% |
| r205 | 3 | 994,43 | non valido (1 escluse) | 0,00% | +0,63% |
| r206 | 3 | 906,14 | +8,18% | +0,83% | +0,83% |
| r207 | 2 | 890,61 | non valido (5 escluse) | +0,90% | +0,47% |
| r208 | 2 | 726,82 | +10,13% | +0,25% | +0,12% |
| r209 | 3 | 909,16 | +17,14% | +0,55% | +0,33% |
| r210 | 3 | 939,37 | +28,18% | +2,32% | +2,15% |
| r211 | 2 | 885,71 | non valido (7 escluse) | +5,70% | +2,46% |
| rc201 | 4 | 1406,94 | +15,03% | 0,00% | +0,47% |
| rc202 | 3 | 1365,65 | non valido (5 escluse) | +0,74% | +1,79% |
| rc203 | 3 | 1049,62 | +14,49% | +2,12% | +2,12% |
| rc204 | 3 | 798,46 | +8,37% | 0,00% | 0,00% |
| rc205 | 4 | 1297,65 | +12,21% | 0,00% | 0,00% |
| rc206 | 3 | 1146,32 | +22,10% | +0,66% | +0,66% |
| rc207 | 3 | 1061,14 | +11,06% | +0,91% | +0,07% |
| rc208 | 3 | 828,14 | +18,04% | +1,30% | +2,15% |

## Risultati sui piani reali («Riduci chilometri e tempi»)

| Piano | Consegne | Mezzi | Prima | Con PyVRP |
|---|---:|---:|---|---|
| 50 | 54 | 6 | 30 servite | **33 servite** (le altre non entrano in turni e capacità) |
| 49 | 25 | 5 | 20 servite | **21 servite** |
| 46 | 41 | 4 | 252,1 km · 14,7 h | **237,7 km · 14,2 h** |
| 42 | 24 | 4 | 526,5 km · 15,4 h | **502,6 km · 14,3 h** |
| 45, 35, 30 | 10–26 | 2–4 | — | identici |
| 48 | 41 | 3 | nessuna servibile (dati del piano) | invariato |

Nessun piano peggiora; i piani con «Distribuisci il lavoro» non usano PyVRP (le piccole
differenze tra un'esecuzione e l'altra vengono dal tempo limitato di OR-Tools, come prima).
I piani 50, 49, 46 e 42 di PyVRP sono stati ricontrollati con il verificatore indipendente:
nessuna violazione di fasce, pause, turni o capacità.

## Scelte del modello e perché

- **Partenza da zero.** Partire dal piano già trovato intrappola PyVRP in piani deboli
  (rc203: 10% dalla migliore nota invece del 2%). Il piano di GiroFacile resta comunque in
  gara nella scelta finale. `FLEET_PYVRP_SEED=1` riattiva la partenza dal piano esistente.
- **Mezzi identici in un solo tipo.** Con ogni mezzo separato la ricerca è molto meno efficace.
- **Partenza libera** fino a fine turno, come il calcolo canonico, che non conta le attese
  eliminabili partendo più tardi: con la partenza fissa nessuna proposta veniva accettata.
- **Consegna esclusa = almeno 100.000 km.** Servire viene prima del risparmio; con valori
  più bassi PyVRP rinunciava a consegne difficili (r104, r211, rc202).
- **Due tentativi.** Prima con le penalità normali di PyVRP; solo se non trova un piano
  valido (giorni in cui non tutto è servibile, come il piano 50) ripete con un tetto delle
  penalità più alto, altrimenti preferirebbe sforare capacità o fasce. Il tetto alto sempre
  attivo peggiorava invece Solomon r104 e r110 (3 consegne escluse).
- **OR-Tools resta.** Sul piano 50 OR-Tools trova a volte giri più corti; girano entrambi e
  vince il migliore.
- **Tempo:** 0,3 s per consegna, tra 1 s e `FLEET_PYVRP_SECONDS` (predefinito 30 s, massimo
  120, 0 lo spegne). Nei test è spento di default e si accende in `tests/test_fleet_pyvrp.py`.

## Limiti noti

- Il calcolo con molte consegne dura di più: con 100 consegne circa 1 minuto e 45 secondi in
  tutto (prima circa 80 s, ma con consegne lasciate fuori).
- PyVRP non ha un costo sulla durata del giro più lungo: «Distribuisci il lavoro» resta
  com'era.
- Serve la libreria `pyvrp==0.14.1` sul server (in `requirements.txt` e `requirements.lock`);
  senza, il calcolo funziona come prima.
