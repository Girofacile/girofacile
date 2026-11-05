# Punteggio dei giri: km più ore dell'autista (5 novembre 2026)

Il calcolo dei giri sceglie, tra i giri che rispettano tutti i vincoli (fasce e orari dei clienti, turni e pause degli autisti, capacità, sponda e ZTL, priorità), quello con il punteggio più basso:

**punteggio = km + ore di lavoro dell'autista × 60**, cioè 1 ora vale 60 km e 1 minuto vale 1 km.

Le ore vanno dalla partenza al rientro, attese comprese. Il peso è fisso e uguale per tutti: non usa prezzi del carburante, consumi o costi orari scritti dal cliente, che possono essere sbagliati o mancare. Prima vincevano sempre i km e un giro con ore di attesa batteva un giro di poco più lungo. Costante: `optimizer.KM_PER_HOUR`.

- Partenza flessibile: se l'autista aspetterebbe l'apertura dei clienti, il giro parte più tardi (multipli di 5 minuti) con lo stesso rientro. Solo l'attesa per l'apertura di una fascia si recupera, non quella dovuta a una pausa a orario fisso. Ricalcolo manuale e secondo passaggio con il traffico mantengono la partenza.
- Multi-mezzo, «Riduci chilometri e tempi»: la ricerca sul punteggio è affiancata da una ricerca di riserva guidata dai soli km (la regola precedente); vince la proposta migliore per consegne servite, attrezzatura e punteggio. Così il calcolo nuovo non restituisce mai un piano che il vecchio batteva su km e ore insieme. Costa da 5 a 20 secondi di calcolo in più sui piani grandi. OR-Tools divide il suo tempo tra una passata sul punteggio e una sui soli km.
- La proposta segnala la partenza spostata e le attese oltre 45 minuti.
- Codice: `optimizer.route_cost`, `departure_slack`, `later_departure`, `solution_key`; ricerca di riserva in `fleet_planning._distribute` (`distance_portfolio`); oracolo dei test in `tests/routing_quality_oracle.py`.

## Confronto sui piani salvati

Ultime 20 pianificazioni multi-mezzo del database locale (il piano 48 non ha consegne servibili), rilanciate senza rete (tratte dalla cache, traffico escluso) con il codice precedente (soli km) e con il nuovo. Punteggio = km + minuti.

| Piano | Fermate | Mezzi | Strategia | km prima → dopo | Ore prima → dopo | Attese (h) prima → dopo | Punteggio prima → dopo |
|---|---|---|---|---|---|---|---|
| 50 | 54 | 6 | riduci km e tempi | 246.5 → 246.5 | 9.5 → 9.5 | 0.0 → 0.0 | 818 → 818 |
| 49 | 25 | 5 | riduci km e tempi | 164.9 → 165.8 | 12.6 → 6.8 | 5.8 → 0.1 | 921 → 574 |
| 47 | 41 | 4 | distribuisci | 280.9 → 280.9 | 30.1 → 21.4 | 17.1 → 8.5 | 2084 → 1564 |
| 46 | 41 | 4 | riduci km e tempi | 230.2 → 252.1 | 33.5 → 14.7 | 22.6 → 3.0 | 2242 → 1131 |
| 45 | 26 | 4 | riduci km e tempi | 421.1 → 428.4 | 26.6 → 13.3 | 13.6 → 0.1 | 2015 → 1224 |
| 42 | 24 | 4 | riduci km e tempi | 460.0 → 526.5 | 24.4 → 15.4 | 10.5 → 0.6 | 1921 → 1450 |
| 35 | 25 | 4 | riduci km e tempi | 586.1 → 628.5 | 29.9 → 18.4 | 12.4 → 0.2 | 2381 → 1732 |
| 34 | 25 | 2 | distribuisci | 194.5 → 194.5 | 9.1 → 8.9 | 3.4 → 3.3 | 740 → 730 |
| 32 | 39 | 5 | distribuisci | 482.5 → 521.0 | 26.8 → 22.6 | 12.1 → 6.8 | 2092 → 1875 |
| 30 | 10 | 2 | riduci km e tempi | 239.2 → 271.5 | 15.8 → 7.1 | 9.5 → 0.0 | 1187 → 696 |
| 29 | 11 | 3 | distribuisci | 415.9 → 415.9 | 14.7 → 13.8 | 3.6 → 2.7 | 1296 → 1241 |
| 24 | 32 | 3 | distribuisci | 508.7 → 508.7 | 23.4 → 23.0 | 8.6 → 8.3 | 1910 → 1890 |
| 20 | 33 | 3 | distribuisci | 645.9 → 628.6 | 23.2 → 22.8 | 4.4 → 4.5 | 2041 → 1999 |
| 19 | 8 | 2 | distribuisci | 533.1 → 533.1 | 9.8 → 9.8 | 0.0 → 0.0 | 1122 → 1122 |
| 18 | 7 | 2 | distribuisci | 109.6 → 109.6 | 3.6 → 3.6 | 0.0 → 0.0 | 329 → 329 |
| 16 | 15 | 3 | distribuisci | 618.4 → 618.4 | 14.6 → 14.6 | 0.0 → 0.0 | 1494 → 1494 |
| 15 | 8 | 2 | distribuisci | 180.0 → 180.0 | 6.0 → 6.0 | 0.0 → 0.0 | 543 → 543 |
| 7 | 5 | 2 | distribuisci | 128.9 → 128.9 | 4.4 → 4.4 | 0.0 → 0.0 | 394 → 394 |
| 6 | 14 | 3 | distribuisci | 628.8 → 628.8 | 13.3 → 13.3 | 0.0 → 0.0 | 1430 → 1430 |

Totale: km 7075.2 → 7267.7, ore 331.4 → 249.5, attese 123.7 → 38.0 h, punteggio 26959 → 22235.
