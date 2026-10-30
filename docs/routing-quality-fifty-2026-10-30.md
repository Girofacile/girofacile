# Cinquanta consegne su 2, 3, 4 e 5 mezzi

Motore esaminato: `b46635be597aa40711173a06a8d10adaaaa71750`. Destinatari, coordinate, carichi e matrice stradale sono identici nei quattro confronti.

Esecuzioni: **64**; copertura completa: **62**; errori operativi inattesi: **0**; richieste esterne: **0**.

**In 2 esecuzioni rimangono consegne fattibili non assegnate**; la copertura minima è 47/50. Il conteggio degli errori sopra riguarda vincoli e consistenza dei piani restituiti: non certifica la massima copertura.

## Condizioni della prova

Ogni consegna pesa 1 kg, occupa un collo e richiede 2 minuti di scarico. Si parte alle 08:00 dallo stesso deposito e si rientra al deposito. La capacità per mezzo è rispettivamente 25, 17, 13 e 10 consegne: servire tutte le cinquanta consegne richiede quindi di utilizzare tutti i mezzi disponibili.

La prova di base ha un turno ampio e nessuna finestra cliente. La seconda prova aggiunge turni, pause e finestre cliente costruite attorno a un itinerario testimone verificato dal simulatore indipendente. Le scadenze del testimone non sono generate dal risultato del motore in esame. Le finestre cliente del profilo vincolato cambiano con il numero di mezzi: le differenze di tempo tra questi quattro profili non dipendono soltanto dalla dimensione della flotta.

Entrambe le strategie sono provate con ordine originale, inverso, mescolato con seme fisso e una ripetizione identica. I tempi sotto sono del solo motore con dati congelati, senza database o provider, e non sono uno SLA di produzione.

## Risultati sull’ordine originale

| Scenario | Mezzi | Strategia | Consegne per mezzo | Servite | km totali | Durata giro più lungo | ms |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: |
| baseline | 2 | Efficiente | 25 / 25 | 50/50 | 72.54 | 145.21 min | 1222.5 |
| baseline | 2 | Bilanciata | 25 / 25 | 50/50 | 81.53 | 151.05 min | 1232.8 |
| constrained | 2 | Efficiente | 25 / 25 | 50/50 | 198.90 | 355.28 min | 1682.3 |
| constrained | 2 | Bilanciata | 25 / 25 | 50/50 | 167.89 | 333.90 min | 1574.3 |
| baseline | 3 | Efficiente | 16 / 17 / 17 | 50/50 | 79.32 | 101.72 min | 712.1 |
| baseline | 3 | Bilanciata | 17 / 17 / 16 | 50/50 | 93.46 | 110.51 min | 961.9 |
| constrained | 3 | Efficiente | 17 / 17 / 16 | 50/50 | 170.98 | 291.82 min | 1168.4 |
| constrained | 3 | Bilanciata | 16 / 17 / 17 | 50/50 | 149.85 | 221.47 min | 1209.8 |
| baseline | 4 | Efficiente | 12 / 12 / 13 / 13 | 50/50 | 117.69 | 95.82 min | 602.1 |
| baseline | 4 | Bilanciata | 12 / 13 / 12 / 13 | 50/50 | 98.27 | 85.05 min | 710.0 |
| constrained | 4 | Efficiente | 12 / 12 / 13 / 13 | 50/50 | 165.13 | 196.88 min | 913.3 |
| constrained | 4 | Bilanciata | 12 / 13 / 12 / 13 | 50/50 | 171.93 | 192.38 min | 1141.4 |
| baseline | 5 | Efficiente | 10 / 10 / 10 / 10 / 10 | 50/50 | 136.67 | 85.68 min | 616.4 |
| baseline | 5 | Bilanciata | 10 / 10 / 10 / 10 / 10 | 50/50 | 115.31 | 74.87 min | 776.8 |
| constrained | 5 | Efficiente | 10 / 10 / 10 / 10 / 10 | 50/50 | 162.28 | 135.92 min | 673.2 |
| constrained | 5 | Bilanciata | 10 / 10 / 10 / 10 / 10 | 50/50 | 143.97 | 97.17 min | 968.5 |

## Qualità e limiti

Cambiando l’ordine degli input, l’obiettivo varia in 27 esecuzioni. Piani peggiori del testimone fattibile secondo la strategia scelta: 2.

**Queste prove non certificano l’ottimo globale di cinquanta consegne.** Misurano copertura, vincoli, stabilità e confronto con un piano fattibile indipendente. Il carico resta 50 kg e 50 colli; cambia la capacità per mezzo: i quattro risultati non rappresentano la stessa flotta con mezzi lasciati inutilizzati.

```sh
python tests/run_routing_quality_fifty.py --strict
python -m pytest tests/test_routing_quality_fifty.py -q
```

Input completi e piani sono salvati in `test-results/routing-quality-fifty/`. Il rapporto precedente rimane separato e conserva i risultati della prima campagna.

## Controesempi di copertura

| Caso | Strategia | Ordine input | Servite | Ripartizione | Consegne non assegnate (ID) |
| --- | --- | --- | ---: | --- | --- |
| fifty-shared-3-constrained | efficient | reverse | 49/50 | 17 / 17 / 15 | 1 |
| fifty-shared-4-constrained | efficient | reverse | 47/50 | 13 / 13 / 12 / 9 | 1, 2, 6 |

Per entrambi i problemi il testimone indipendente e l’esecuzione con ordine originale servono tutte le cinquanta consegne. Le esclusioni osservate non dimostrano quindi un’impossibilità operativa: mostrano un limite della ricerca euristica globale.
