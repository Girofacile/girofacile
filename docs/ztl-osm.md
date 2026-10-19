# Rilevamento ZTL informativo con OpenStreetMap

GiroFacile segnala le consegne le cui **coordinate gia' verificate** ricadono nei perimetri ZTL disponibili in OpenStreetMap (`boundary=limited_traffic_zone`). Non determina diritti di accesso, orari, deroghe o autorizzazioni. L'avviso **non impedisce la pianificazione** e non modifica il percorso stradale.

## Prima attivazione e aggiornamento

L'archivio di perimetri non e' incluso nel codice: prima dell'utilizzo e' necessario caricare i dati geografici OpenStreetMap.

In installazione locale:

```bash
python -m scripts.update_ztl_osm
```

In un'installazione Docker Compose, il servizio dedicato `ztl-updater` recupera l'archivio al suo avvio e poi automaticamente ogni **7 giorni** (riprovando dopo 12 ore in caso di errore). Per aggiornare manualmente senza aspettare il ciclo:

```bash
docker compose exec girofacile python -m scripts.update_ztl_osm
```

Il comando scarica le geometrie ZTL italiane da Overpass (fonte OpenStreetMap), genera `data/ztl/ztl_osm.geojson` e sostituisce atomicamente il file precedente **solo se** sono state recuperate geometrie valide. In Docker la directory e' montata dal filesystem host, quindi il file persiste al riavvio/ricreazione del container. Lo stesso archivio viene condiviso da tutte le aziende; non contiene indirizzi o dati personali.

In installazione locale non-Docker, predisporre l'aggiornamento **approssimativamente una volta a settimana** con scheduler di sistema (cron o timer), preferibilmente in orari di basso carico. Non eseguire l'aggiornamento a ogni richiesta e rispettare le policy/limitazioni dell'istanza pubblica Overpass; in caso di problemi la versione precedente viene mantenuta. L'endpoint Overpass puo' essere configurato con `GF_ZTL_OVERPASS_URL`, e l'User-Agent con `GF_ZTL_USER_AGENT`. Percorso alternativo: `GIROFACILE_ZTL_GEOJSON`.

## Dove compare l'avviso

- Cliente: il campo `ztl` preesistente resta la marcatura **manuale**; l'API espone la marcatura effettiva (`ztl = manuale OR rilevamento OSM`), l'origine e il nome dell'area quando presente.
- Ordine indipendente dal cliente: usa la posizione confermata nell'`address_verification`; la marcatura operativa manuale resta valida.
- Pianificazione e anteprima: mostra l'avviso «Verifica i permessi di accesso del tuo mezzo». Non cambia routing, fasce orarie o blocchi di pianificazione.
- Indirizzi senza latitudine/longitudine verificata: **nessuna chiamata automatica a Google** viene aggiunta. Il rilevamento parte con le coordinate che il flusso esistente acquisisce durante la normale verifica dell'indirizzo.

La presenza di un poligono fa scattare una segnalazione. L'assenza di una corrispondenza **non garantisce** l'assenza di una ZTL: la mappatura OpenStreetMap e' collaborativa e puo' essere incompleta, imprecisa o non aggiornata. Il sistema distingue tra `non_rilevata` e `non_disponibile` (file o coordinate mancanti). Chi ha informazioni locali puo' continuare a utilizzare il flag manuale preesistente.

## Licenza, attribuzione e limiti

Fonte unica dei perimetri: **© OpenStreetMap contributors**, dati disponibili secondo la **Open Database License (ODbL)**. Vedere https://www.openstreetmap.org/copyright. Conservare l'attribuzione e valutare gli obblighi di condivisione/derivazione della ODbL qualora si distribuiscano database derivati.

La classificazione usata e' `boundary=limited_traffic_zone`. Non tutte le restrizioni di accesso sono mappate con quel tag e non tutte le geometrie OSM disponibili garantiscono la chiusura completa del poligono. Il convertitore ignora le geometrie incomplete, non prova a inferire perimetri da segmenti incompleti e non sostituisce alcuna verifica normativa delle ZTL.

## Verifiche

```bash
python -m pytest tests/test_ztl_detection.py -q
```

In un ambiente reale verificare indirizzi noti dentro e fuori ZTL con il file aggiornato, oltre al comportamento con un archivio assente.
