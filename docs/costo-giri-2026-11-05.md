# Costo dei giri: carburante più ore dell'autista (5 novembre 2026)

Il calcolo dei giri sceglie il giro che costa meno: km per il costo al km del mezzo (consumo per prezzo dell'energia, 0,20 €/km se mancano i dati) più le ore dell'autista (Impostazioni, 15 €/ora se vuoto), attese comprese. Prima vincevano sempre i km e le attese contavano solo a parità di km e minuti.

- Partenza flessibile: se l'autista aspetterebbe l'apertura dei clienti, il giro parte più tardi (multipli di 5 minuti) con lo stesso rientro. Solo l'attesa per l'apertura di una fascia si recupera, non quella dovuta a una pausa a orario fisso. Ricalcolo manuale e secondo passaggio con il traffico mantengono la partenza.
- Multi-mezzo: stesse chiavi di confronto (costo, poi km e minuti); OR-Tools divide il tempo tra una passata sul costo e una sui soli km e resta la proposta migliore. La proposta segnala la partenza spostata e le attese oltre 45 minuti.
- Codice: `app/services/route_costs.py`, `optimizer.route_cost`, `departure_slack`, `later_departure`, `solution_key`; oracolo dei test in `tests/routing_quality_oracle.py`.

## Confronto sui piani salvati

Ultime 20 pianificazioni multi-mezzo del database locale, rilanciate senza rete (tratte dalla cache, traffico escluso) con il codice precedente e con il nuovo; costi con i mezzi veri e 15 €/ora.

| Piano | Fermate | Mezzi | Strategia | km prima → dopo | Ore prima → dopo | Attese (h) prima → dopo | Costo € prima → dopo |
|---|---|---|---|---|---|---|---|
| 50 | 54 | 6 | riduci km e tempi | 246.5 → 310.2 | 9.5 → 11.9 | 0.0 → 0.0 | 174.5 → 234.6 |
| 49 | 25 | 5 | riduci km e tempi | 164.9 → 168.2 | 12.6 → 6.6 | 5.8 → 0.0 | 209.0 → 119.6 |
| 47 | 41 | 4 | distribuisci | 280.9 → 280.9 | 30.1 → 21.4 | 17.1 → 8.5 | 493.2 → 363.2 |
| 46 | 41 | 4 | riduci km e tempi | 230.2 → 252.1 | 33.5 → 14.7 | 22.6 → 3.0 | 552.9 → 275.3 |
| 45 | 26 | 4 | riduci km e tempi | 421.1 → 433.6 | 26.6 → 13.3 | 13.6 → 0.1 | 455.2 → 257.8 |
| 42 | 24 | 4 | riduci km e tempi | 460.0 → 509.8 | 24.4 → 15.1 | 10.5 → 0.8 | 422.6 → 284.7 |
| 35 | 25 | 4 | riduci km e tempi | 586.1 → 655.4 | 29.9 → 18.3 | 12.4 → 0.2 | 537.4 → 355.0 |
| 34 | 25 | 2 | distribuisci | 194.5 → 194.5 | 9.1 → 8.9 | 3.4 → 3.3 | 150.3 → 147.8 |
| 32 | 39 | 5 | distribuisci | 482.5 → 514.2 | 26.8 → 22.5 | 12.1 → 6.8 | 464.7 → 394.0 |
| 30 | 10 | 2 | riduci km e tempi | 239.2 → 272.7 | 15.8 → 7.1 | 9.5 → 0.0 | 267.4 → 126.5 |
| 29 | 11 | 3 | distribuisci | 415.9 → 415.9 | 14.7 → 13.8 | 3.6 → 2.7 | 266.8 → 253.1 |
| 24 | 32 | 3 | distribuisci | 508.7 → 508.7 | 23.4 → 23.0 | 8.6 → 8.3 | 419.5 → 414.5 |
| 20 | 33 | 3 | distribuisci | 645.9 → 645.9 | 23.2 → 22.5 | 4.4 → 3.7 | 425.1 → 413.9 |
| 19 | 8 | 2 | distribuisci | 533.1 → 533.1 | 9.8 → 9.8 | 0.0 → 0.0 | 218.2 → 218.2 |
| 18 | 7 | 2 | distribuisci | 109.6 → 109.6 | 3.6 → 3.6 | 0.0 → 0.0 | 71.1 → 71.1 |
| 16 | 15 | 3 | distribuisci | 618.4 → 618.4 | 14.6 → 14.6 | 0.0 → 0.0 | 301.2 → 301.2 |
| 15 | 8 | 2 | distribuisci | 180.0 → 180.0 | 6.0 → 6.0 | 0.0 → 0.0 | 117.5 → 117.5 |
| 7 | 5 | 2 | distribuisci | 128.9 → 128.9 | 4.4 → 4.4 | 0.0 → 0.0 | 85.4 → 85.4 |
| 6 | 14 | 3 | distribuisci | 628.8 → 628.8 | 13.3 → 13.3 | 0.0 → 0.0 | 286.8 → 286.8 |

Totale: km 7075.2 → 7360.9, ore 331.4 → 250.9, attese 123.7 → 37.4 h, costo 5918.9 → 4720.2 €.

Caso peggiorato: piano 50, prova con 54 consegne di cui 24 che non entrano in nessun mezzo e 2 autisti utilizzabili. La ricerca sceglie un altro insieme di consegne servite e costa di più (174,5 → 234,6 €). La passata di OR-Tools sul costo trovava 200,9 € ma metteva una consegna su un mezzo senza l'attrezzatura richiesta, che ha la precedenza sul costo. Da riprendere se si presenta con dati reali.
