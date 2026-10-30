# Verifica del motore corrente — 30 ottobre 2026

Versione esaminata: `2220304753a73e85656ca3b50829a008d6c3aba4`. Nuovi casi sintetici, matrici stradali congelate e riferimento indipendente; nessun vecchio scenario riutilizzato.

70 problemi nuovi, 283 esecuzioni; 240 confronti con ottimo dimostrato, 1 scarto dall’ottimo (inclusi i casi oltre la soglia esatta del motore). Errori di correttezza o delle garanzie dichiarate: 0. Richieste esterne: 0.

## Valutazione e problemi concreti

Il motore supera i controlli di capacità, orari, pause, disponibilità e unicità delle consegne sui casi verificati. Nei problemi piccoli con ricerca esatta non sono emerse promesse di ottimalità violate. Sulla campagna completa, **239 dei 240 confronti con ottimo indipendente coincidono con il riferimento**; il confronto restante dimostra un limite dell’euristica della flotta oltre la soglia globale di sette consegne.

Il controesempio `fleet-new-scale-8`, strategia bilanciata e input inverso, serve tutte le otto consegne con due mezzi da quattro posti. Ogni ordine interno ai due giri è già ottimizzato: la differenza nasce dalla ripartizione delle consegne tra mezzi.

| Indicatore | Risultato del motore | Ottimo indipendente | Scarto |
| --- | ---: | ---: | ---: |
| Durata del giro più lungo | 50,06 min | 46,43 min | +7,80% |
| Durata cumulativa | 97,58 min | 87,66 min | +11,31% |
| Distanza cumulativa | 38,67 km | 33,33 km | +16,01% |

Con l’ordine originale delle stesse consegne, il motore trova l’ottimo. Ripetendo input identici il risultato rimane stabile: la sensibilità è all’ordine in ingresso, non casualità tra esecuzioni identiche. L’oracolo indipendente enumera anche le assegnazioni di questo caso da otto consegne; il motore usa invece l’euristica oltre sette. `--strict` controlla i vincoli e le garanzie dichiarate, mentre registra questo scarto euristico senza fingere che sia un errore di capacità o una falsa promessa del motore.

Un secondo difetto riguarda le nuove card carburante: con prezzo manuale **0**, l’anteprima calcola costo zero ma il salvataggio sostituisce il valore con **1,75**. La causa è il fallback tramite `or` in `app/routers/routes.py:477`. Il nuovo test dedicato è marcato `xfail(strict=True)` con motivo esplicito: documenta il difetto e richiederà la rimozione del marcatore quando verrà corretto. Non sono stati modificati algoritmo, dati operativi o vecchi test.

Le altre cinque nuove prove API hanno verificato turni/pause per risorsa, revisione e programmazione, prezzi energetici conservati, disponibilità derivata da un impegno reale, margine prudente e rifiuto degli input incoerenti. L’oracolo ha inoltre venti controlli con risultati calcolati a mano; otto ulteriori controlli verificano che il nuovo auditor rilevi risposte invalide o peggiori del riferimento.

## Portata della verifica

- **42 casi di giro singolo e 28 casi di flotta**, con 283 esecuzioni comprese permutazioni e ripetizioni; da due a cento consegne e fino a dieci risorse.
- **96 confronti singoli esatti** e **144 confronti flotta esatti**; un solo scarto, nel caso euristico da otto consegne descritto sopra.
- Nessuna duplicazione, violazione operativa inattesa, mutazione degli input o richiesta esterna nella campagna. È presente anche un caso non fattibile con scadenza troppo stretta: il riferimento conferma che nessun ordine delle fermate può rispettarla; non viene dichiarato un ottimo del vecchio punteggio di ritardo.
- I test grandi verificano fattibilità e confronto con testimoni noti; **non dimostrano l’ottimo globale per cento consegne**. Le tredici esecuzioni con certificato analitico provano soltanto la minima distanza su problemi in linea retta.
- Le matrici sono sintetiche e congelate. I risultati non misurano il traffico reale futuro né dimostrano risparmi commerciali su giri dei clienti.

Per la flotta, `max_minutes` nel generatore rappresenta il tempo disponibile prima di altri impegni o della fine della giornata, **non** il vecchio limite configurabile eliminato dall’interfaccia. Le prove API usano anche un impegno realmente salvato nel database isolato.

Il prezzo energetico e l’alimentazione influenzano la stima economica, non la scelta dell’assegnazione. Volume, pallet, refrigerazione e transpallet non sono vincoli automatici dell’ottimizzatore attuale. ZTL e sponda sono preferenze con avviso. Partenza comune e turni nella stessa giornata restano assunzioni del modello; non sono state inventate funzionalità per finestre notturne o orari tassativi assenti dal codice.

La prossima miglioria più concreta è rendere più robusta l’assegnazione globale vicino alla soglia sette/otto e verificare la stessa istanza con più ordini iniziali. Il bug del prezzo zero richiede una correzione separata del salvataggio. Questa attività consegna la valutazione e la nuova base di test, senza alterare il comportamento del motore durante la misura.

## Criteri

- Giro singolo: fattibilità, poi chilometri, durata, attesa e avvisi.
- Flotta efficiente: consegne servite, compatibilità preferenziale, meno mezzi, durata cumulativa e km.
- Flotta bilanciata: consegne servite, compatibilità preferenziale, più mezzi utilizzati, durata massima, bilanciamento, durata cumulativa e km.
- Il prezzo energetico modifica la stima, non l’obiettivo di assegnazione.

Il riferimento esatto enumera ordini e assegnazioni sui casi piccoli. Sui casi grandi un testimone fattibile è un termine di confronto, non una prova di ottimalità; i casi in linea retta hanno un limite inferiore dimostrabile per i km. Un ottimo dell’ordine di un giro con mezzi e consegne fissati non prova l’ottimo globale della flotta.

## Risultati per problema (prima esecuzione)

| Caso | Strategia | Fermate | Servite | Mezzi | km | Minuti cumulativi | Riferimento | Esito | ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: |
| single-q30-shorter-is-slower | single | 3 | 3 | 1 | 9.0 | 76.0 | ottimo esatto | coerente | 108.799 |
| single-q30-terminal-closed | single | 4 | 4 | 1 | 26.8 | 32.0 | ottimo esatto | coerente | 0.705 |
| single-q30-terminal-open | single | 4 | 4 | 1 | 5.6 | 24.0 | ottimo esatto | coerente | 0.765 |
| single-q30-urgent-detour | single | 5 | 5 | 1 | 46.400000000000006 | 96.0 | fattibilità esatta | single_route_infeasible_no_feasible_reference | 5.669 |
| single-q30-second-window-is-needed | single | 4 | 4 | 1 | 17.0 | 82.0 | ottimo esatto | coerente | 1.309 |
| single-q30-service-finishes-on-boundary | single | 3 | 3 | 1 | 8.0 | 40.5 | ottimo esatto | coerente | 0.298 |
| single-q30-pause-interrupts-driving | single | 4 | 4 | 1 | 20.0 | 89.0 | ottimo esatto | coerente | 1.033 |
| single-q30-pause-forbids-split-unloading | single | 3 | 3 | 1 | 9.2 | 94.0 | ottimo esatto | coerente | 0.347 |
| single-q30-waiting-covers-pause | single | 4 | 4 | 1 | 20.5 | 127.0 | ottimo esatto | coerente | 1.267 |
| single-q30-shift-end-beats-shorter-distance | single | 3 | 3 | 1 | 19.5 | 35.0 | ottimo esatto | coerente | 0.248 |
| single-q30-load-exactly-at-both-caps | single | 4 | 4 | 1 | 33.6 | 70.0 | ottimo esatto | coerente | 0.977 |
| single-q30-equipment-remains-warning | single | 4 | 4 | 1 | 30.9 | 90.0 | ottimo esatto | coerente | 0.628 |
| single-q30-crosses-midnight | single | 4 | 4 | 1 | 43.1 | 67.0 | ottimo esatto | coerente | 0.632 |
| single-q30-rejects-capacity-overrun | single | 2 | — | — | — | — | validazione | coerente | 0.04 |
| single-q30-seeded-3-20261333-plain | single | 3 | 3 | 1 | 45.4 | 65.0 | ottimo esatto | coerente | 0.318 |
| single-q30-seeded-3-20261334-windows | single | 3 | 3 | 1 | 31.0 | 98.0 | ottimo esatto | coerente | 0.329 |
| single-q30-seeded-3-20261335-plain | single | 3 | 3 | 1 | 41.1 | 46.0 | ottimo esatto | coerente | 0.278 |
| single-q30-seeded-3-20261336-windows | single | 3 | 3 | 1 | 39.0 | 68.0 | ottimo esatto | coerente | 0.418 |
| single-q30-seeded-3-20261337-plain | single | 3 | 3 | 1 | 31.0 | 87.0 | ottimo esatto | coerente | 0.286 |
| single-q30-seeded-4-20261434-plain | single | 4 | 4 | 1 | 36.5 | 85.0 | ottimo esatto | coerente | 0.725 |
| single-q30-seeded-4-20261435-windows | single | 4 | 4 | 1 | 28.6 | 101.0 | ottimo esatto | coerente | 1.131 |
| single-q30-seeded-4-20261436-plain | single | 4 | 4 | 1 | 37.199999999999996 | 101.0 | ottimo esatto | coerente | 0.65 |
| single-q30-seeded-4-20261437-windows | single | 4 | 4 | 1 | 77.6 | 95.0 | ottimo esatto | coerente | 1.173 |
| single-q30-seeded-4-20261438-plain | single | 4 | 4 | 1 | 22.1 | 77.0 | ottimo esatto | coerente | 0.889 |
| single-q30-seeded-5-20261535-plain | single | 5 | 5 | 1 | 34.7 | 125.0 | ottimo esatto | coerente | 3.799 |
| single-q30-seeded-5-20261536-windows | single | 5 | 5 | 1 | 65.4 | 121.0 | ottimo esatto | coerente | 6.824 |
| single-q30-seeded-5-20261537-plain | single | 5 | 5 | 1 | 41.599999999999994 | 81.0 | ottimo esatto | coerente | 3.813 |
| single-q30-seeded-5-20261538-windows | single | 5 | 5 | 1 | 54.400000000000006 | 103.0 | ottimo esatto | coerente | 5.513 |
| single-q30-seeded-5-20261539-plain | single | 5 | 5 | 1 | 35.5 | 89.0 | ottimo esatto | coerente | 3.263 |
| single-q30-seeded-6-20261636-plain | single | 6 | 6 | 1 | 39.699999999999996 | 98.0 | ottimo esatto | coerente | 26.538 |
| single-q30-seeded-6-20261637-windows | single | 6 | 6 | 1 | 88.0 | 131.0 | ottimo esatto | coerente | 38.054 |
| single-q30-seeded-6-20261638-plain | single | 6 | 6 | 1 | 20.400000000000002 | 109.0 | ottimo esatto | coerente | 24.273 |
| single-q30-seeded-6-20261639-windows | single | 6 | 6 | 1 | 82.7 | 124.0 | ottimo esatto | coerente | 34.557 |
| single-q30-seeded-6-20261640-plain | single | 6 | 6 | 1 | 49.099999999999994 | 131.0 | ottimo esatto | coerente | 33.929 |
| single-q30-line-certificate-9 | single | 9 | 9 | 1 | 30.599999999999994 | 45.80999999999983 | limite km | minimum_distance_certified_by_bound | 23.308 |
| single-q30-line-certificate-12 | single | 12 | 12 | 1 | 40.79999999999999 | 61.079999999999814 | limite km | minimum_distance_certified_by_bound | 94.156 |
| single-q30-line-certificate-20 | single | 20 | 20 | 1 | 68.0 | 101.79999999999961 | limite km | minimum_distance_certified_by_bound | 139.089 |
| single-q30-line-certificate-50 | single | 50 | 50 | 1 | 169.99999999999972 | 254.49999999999795 | limite km | minimum_distance_certified_by_bound | 450.106 |
| single-q30-line-certificate-100 | single | 100 | 100 | 1 | 339.99999999999915 | 508.9999999999968 | limite km | minimum_distance_certified_by_bound | 2318.031 |
| single-q30-seeded-9-20261209-windows | single | 9 | 9 | 1 | 122.19999999999999 | 159.0 | testimone | coerente | 119.434 |
| single-q30-seeded-16-20261216-windows | single | 16 | 16 | 1 | 215.89999999999998 | 246.0 | testimone | coerente | 368.528 |
| single-q30-seeded-24-20261224-windows | single | 24 | 24 | 1 | 269.19999999999993 | 349.0 | testimone | coerente | 509.833 |
| fleet-new-weight-repacking | efficient | 6 | 6 | 2 | 21.6 | 68.0 | ottimo esatto | coerente | 63.135 |
| fleet-new-weight-repacking | balanced | 6 | 6 | 2 | 21.6 | 68.0 | ottimo esatto | coerente | 10.793 |
| fleet-new-parcels-repacking | efficient | 6 | 6 | 2 | 21.6 | 74.0 | ottimo esatto | coerente | 10.851 |
| fleet-new-parcels-repacking | balanced | 6 | 6 | 2 | 21.6 | 74.0 | ottimo esatto | coerente | 13.232 |
| fleet-new-soft-equipment | efficient | 5 | 5 | 2 | 18.900000000000002 | 69.0 | ottimo esatto | coerente | 9.375 |
| fleet-new-soft-equipment | balanced | 5 | 5 | 2 | 18.900000000000002 | 69.0 | ottimo esatto | coerente | 8.846 |
| fleet-new-coverage-before-equipment | efficient | 4 | 4 | 2 | 16.200000000000003 | 58.0 | ottimo esatto | coerente | 2.967 |
| fleet-new-coverage-before-equipment | balanced | 4 | 4 | 2 | 16.200000000000003 | 58.0 | ottimo esatto | coerente | 1.982 |
| fleet-new-urgent-stop-break-conflict | efficient | 5 | 5 | 2 | 18.900000000000002 | 131.0 | ottimo esatto | coerente | 10.36 |
| fleet-new-urgent-stop-break-conflict | balanced | 5 | 5 | 2 | 18.900000000000002 | 131.0 | ottimo esatto | coerente | 9.122 |
| fleet-new-shift-start-is-not-delayed | efficient | 4 | 4 | 1 | 13.5 | 104.0 | ottimo esatto | coerente | 4.55 |
| fleet-new-shift-start-is-not-delayed | balanced | 4 | 4 | 1 | 13.5 | 104.0 | ottimo esatto | coerente | 5.224 |
| fleet-new-upcoming-bookings | efficient | 6 | 6 | 1 | 18.9 | 102.0 | ottimo esatto | coerente | 238.735 |
| fleet-new-upcoming-bookings | balanced | 6 | 6 | 3 | 24.300000000000004 | 114.0 | ottimo esatto | coerente | 234.601 |
| fleet-new-return-through-break | efficient | 3 | 3 | 1 | 10.8 | 49.0 | ottimo esatto | coerente | 3.274 |
| fleet-new-return-through-break | balanced | 3 | 3 | 2 | 13.500000000000002 | 59.0 | ottimo esatto | coerente | 3.401 |
| fleet-new-return-policy-open | efficient | 4 | 4 | 2 | 10.8 | 56.0 | ottimo esatto | coerente | 4.571 |
| fleet-new-return-policy-open | balanced | 4 | 4 | 2 | 10.8 | 56.0 | ottimo esatto | coerente | 3.52 |
| fleet-new-return-policy-closed | efficient | 4 | 2 | 2 | 10.8 | 68.0 | ottimo esatto | coerente | 4.535 |
| fleet-new-return-policy-closed | balanced | 4 | 2 | 2 | 10.8 | 68.0 | ottimo esatto | coerente | 2.919 |
| fleet-new-zero-and-unlimited-capacity | efficient | 4 | 4 | 1 | 13.5 | 51.0 | ottimo esatto | coerente | 5.435 |
| fleet-new-zero-and-unlimited-capacity | balanced | 4 | 4 | 2 | 16.200000000000003 | 58.0 | ottimo esatto | coerente | 5.058 |
| fleet-new-two-service-windows | efficient | 5 | 5 | 2 | 18.900000000000002 | 684.0 | ottimo esatto | coerente | 11.762 |
| fleet-new-two-service-windows | balanced | 5 | 5 | 2 | 18.900000000000002 | 684.0 | ottimo esatto | coerente | 8.123 |
| fleet-new-availability-ceil-boundary | efficient | 2 | 2 | 2 | 10.8 | 70.0 | ottimo esatto | coerente | 0.416 |
| fleet-new-availability-ceil-boundary | balanced | 2 | 2 | 2 | 10.8 | 70.0 | ottimo esatto | coerente | 0.439 |
| fleet-new-availability-ceil-over | efficient | 2 | 1 | 1 | 5.4 | 35.00001999999995 | ottimo esatto | coerente | 0.371 |
| fleet-new-availability-ceil-over | balanced | 2 | 1 | 1 | 5.4 | 35.00001999999995 | ottimo esatto | coerente | 0.552 |
| fleet-new-prudent-margin-1.0 | efficient | 3 | 3 | 2 | 13.500000000000002 | 65.0 | ottimo esatto | coerente | 0.806 |
| fleet-new-prudent-margin-1.0 | balanced | 3 | 3 | 2 | 13.500000000000002 | 65.0 | ottimo esatto | coerente | 0.887 |
| fleet-new-prudent-margin-1.15 | efficient | 3 | 2 | 1 | 8.100000000000001 | 44.5 | ottimo esatto | coerente | 1.143 |
| fleet-new-prudent-margin-1.15 | balanced | 3 | 2 | 2 | 10.8 | 56.0 | ottimo esatto | coerente | 1.515 |
| fleet-new-energy-prices-per-resource | efficient | 3 | 3 | 2 | 21.5 | 47.0 | ottimo esatto | coerente | 0.616 |
| fleet-new-energy-prices-per-resource | balanced | 3 | 3 | 2 | 21.5 | 47.0 | ottimo esatto | coerente | 0.728 |
| fleet-new-random-2026103000 | efficient | 5 | 5 | 2 | 35.348532459187176 | 92.49992757902044 | ottimo esatto | coerente | 7.886 |
| fleet-new-random-2026103000 | balanced | 5 | 5 | 2 | 35.348532459187176 | 92.49992757902044 | ottimo esatto | coerente | 7.657 |
| fleet-new-random-2026103001 | efficient | 6 | 6 | 2 | 52.70502819607885 | 141.05088590217508 | ottimo esatto | coerente | 68.262 |
| fleet-new-random-2026103001 | balanced | 6 | 6 | 2 | 52.70502819607885 | 141.05088590217508 | ottimo esatto | coerente | 74.155 |
| fleet-new-random-2026103002 | efficient | 5 | 5 | 2 | 22.855238013708185 | 81.28230073343997 | ottimo esatto | coerente | 19.433 |
| fleet-new-random-2026103002 | balanced | 5 | 5 | 2 | 29.11845657126608 | 92.921910442176 | ottimo esatto | coerente | 27.814 |
| fleet-new-random-2026103003 | efficient | 6 | 6 | 2 | 38.77653491221129 | 135.6581422236112 | ottimo esatto | coerente | 34.224 |
| fleet-new-random-2026103003 | balanced | 6 | 6 | 2 | 38.77653491221129 | 135.6581422236112 | ottimo esatto | coerente | 35.22 |
| fleet-new-random-2026103004 | efficient | 5 | 5 | 2 | 24.147041574510702 | 76.68299761634728 | ottimo esatto | coerente | 14.299 |
| fleet-new-random-2026103004 | balanced | 5 | 5 | 2 | 24.147041574510702 | 76.68299761634728 | ottimo esatto | coerente | 11.493 |
| fleet-new-random-2026103005 | efficient | 6 | 6 | 2 | 43.60796345467719 | 131.82478731703577 | ottimo esatto | coerente | 45.918 |
| fleet-new-random-2026103005 | balanced | 6 | 6 | 2 | 43.60796345467719 | 131.82478731703577 | ottimo esatto | coerente | 69.972 |
| fleet-new-scale-8 | efficient | 8 | 8 | 2 | 31.507229166550324 | 84.27892145996077 | ottimo esatto | coerente | 17.719 |
| fleet-new-scale-8 | balanced | 8 | 8 | 2 | 33.32911659658362 | 87.66472995825279 | ottimo esatto | coerente | 19.788 |
| fleet-new-scale-12 | efficient | 12 | 12 | 3 | 39.77557539734205 | 112.50770649063577 | testimone | coerente | 17.41 |
| fleet-new-scale-12 | balanced | 12 | 12 | 3 | 41.13034432328163 | 115.02541865388639 | testimone | coerente | 48.447 |
| fleet-new-scale-25 | efficient | 25 | 25 | 4 | 78.45561740667517 | 224.00689960532554 | testimone | coerente | 324.667 |
| fleet-new-scale-25 | balanced | 25 | 25 | 4 | 60.72038630789187 | 191.0476205721884 | testimone | coerente | 315.571 |
| fleet-new-scale-50 | efficient | 50 | 50 | 5 | 135.93009076445222 | 406.10459345606176 | testimone | coerente | 701.627 |
| fleet-new-scale-50 | balanced | 50 | 50 | 5 | 96.77622653150542 | 333.340774970054 | testimone | coerente | 1001.604 |
| fleet-new-scale-100 | efficient | 100 | 100 | 10 | 292.1174072802197 | 849.8553586623549 | testimone | coerente | 424.508 |
| fleet-new-scale-100 | balanced | 100 | 100 | 10 | 201.58138214642725 | 681.6025685907053 | testimone | coerente | 546.698 |

## Robustezza e prestazioni

Variazioni dell’obiettivo riordinando gli input: 1. Risultati peggiori di un testimone fattibile: 0. Certificati di distanza minima sui casi analitici: 13.

I tempi misurano il motore su questa macchina, senza latenza database/provider; non sono tempi garantiti in produzione. Percentili sulle esecuzioni della campagna, non su un carico reale.

```json
{
  "single": {
    "median": 1.134,
    "p95": 368.528,
    "maximum": 2318.031
  },
  "fleet": {
    "median": 9.859,
    "p95": 368.449,
    "maximum": 1113.55
  }
}
```

## Riproduzione

```sh
python tests/run_routing_quality_audit.py --profile full --strict
python -m pytest tests/test_routing_quality_oracle.py tests/test_routing_quality_audit.py tests/test_routing_quality_integration.py -q -ra
```

Il runner salva input completi, piani, risultati e hash dei sorgenti in `test-results/routing-quality/`. `--profile quick` riduce la campagna per la CI. `--strict` fallisce per violazioni o scarti nei casi in cui il motore dichiara ricerca esatta; i gap euristici, anche quando dimostrati con un riferimento esatto più ampio, restano esplicitamente visibili nel rapporto.
