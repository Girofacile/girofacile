# CHANGELOG V89.5

- Aggiunte alimentazioni mezzo: Gasolio, Benzina, GPL, Metano, Elettrico, Ibrido benzina/diesel e Plug-in benzina/diesel.
- Aggiunti consumi specifici L/100 km, kg/100 km e kWh/100 km.
- La pianificazione mostra il costo energia coerente con il mezzo selezionato.
- Modalità prezzo manuale o automatico MIMIT per Gasolio, Benzina, GPL e Metano.
- Il prezzo automatico viene memorizzato giornalmente nel database; se il MIMIT non è raggiungibile viene usato l'ultimo dato disponibile.
- Per elettrico e componente elettrica dei plug-in resta disponibile la tariffa manuale aziendale in €/kWh.
- Il giro salva uno snapshot di alimentazione, consumi, prezzi e quantità energetiche usate, preservando lo storico costi.
