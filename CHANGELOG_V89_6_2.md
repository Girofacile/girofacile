# GiroFacile V89.6.2 — MyCarPlate

- Aggiunto provider `mycarplate` per il recupero reale dei dati veicolo da targa italiana.
- Configurazione tramite `MYCARPLATE_API_KEY` nel file `.env`.
- Gestiti errori di autenticazione, targa non trovata, limite gratuito e indisponibilità del servizio.
- Mapping automatico di marca, modello, versione, anno, alimentazione, cilindrata, potenza, classe emissioni e carrozzeria quando disponibili.
- Mantiene compatibilità con i provider `free` e `openapi`.
