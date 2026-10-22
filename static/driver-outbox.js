/* Esiti dell'autista in attesa di rete.
 * Se l'invio fallisce per rete assente o server momentaneamente non raggiungibile,
 * l'esito resta sul telefono e parte appena la connessione torna. Il server accetta
 * le ripetizioni dello stesso esito, quindi un invio doppio non crea duplicati. */
(function(root){
  'use strict';
  const RETRY_STATUSES = new Set([0, 401, 408, 429, 502, 503, 504]);

  function create({storage, send, key, onChange}={}){
    let items = [];
    let flushing = null;
    const changed = () => { if(onChange) onChange(items.slice()); };

    function load(){
      try { items = JSON.parse(storage?.getItem(key) || '[]'); }
      catch(e) { items = []; }
      if(!Array.isArray(items)) items = [];
    }
    // Se il telefono non ha spazio l'esito resta comunque in memoria finché la pagina è aperta.
    function save(){
      try { storage?.setItem(key, JSON.stringify(items)); return true; }
      catch(e) { return false; }
    }

    function add(item){
      // Un nuovo esito per la stessa consegna e azione sostituisce quello precedente.
      items = items.filter(x => !(x.deliveryId === item.deliveryId && x.kind === item.kind));
      items.push({...item, queuedAt: item.queuedAt || new Date().toISOString()});
      const persisted = save();
      changed();
      return persisted;
    }

    function pending(routeId){
      return items.filter(x => routeId == null || Number(x.routeId) === Number(routeId));
    }

    // Invia in ordine; si ferma al primo errore di rete per non saltare esiti.
    function flush(){
      if(flushing) return flushing;
      flushing = (async () => {
        const rejected = [];
        while(items.length){
          const item = items[0];
          try { await send(item); }
          catch(e) {
            if(isRetryable(e)) break;
            rejected.push({item, message: e.message});
          }
          items = items.slice(1);
          save();
          changed();
        }
        return rejected;
      })().finally(() => { flushing = null; });
      return flushing;
    }

    load();
    return {add, pending, flush, count: () => items.length};
  }

  function isRetryable(error){
    return !!error && (error.offline === true || RETRY_STATUSES.has(Number(error.status)));
  }

  // Applica gli esiti in attesa ai dati del giro ricevuti dal server.
  function overlay(data, pendingItems){
    if(!data?.consegne || !pendingItems?.length) return data;
    const outcome = {complete: 'completata', missed: 'mancata'};
    for(const item of pendingItems){
      const delivery = data.consegne.find(c => Number(c.id) === Number(item.deliveryId));
      if(!delivery) continue;
      if(outcome[item.kind] && delivery.status === 'in_attesa'){
        delivery.status = outcome[item.kind];
        if(item.kind === 'missed') delivery.motivo_mancata = item.body?.motivo;
        if(item.kind === 'complete') delivery.tempo_scarico_effettivo = item.body?.tempo_scarico;
        if(item.body?.note) delivery.note_operatore = item.body.note;
      }
      if(item.kind === 'note') delivery.note_operatore = item.body?.note || null;
      delivery.in_attesa_invio = true;
    }
    const done = data.consegne.filter(c => c.status === 'completata').length;
    const missed = data.consegne.filter(c => c.status === 'mancata').length;
    const total = data.consegne.length;
    const next = data.consegne.findIndex(c => c.status === 'in_attesa');
    data.progress = {...data.progress, totale: total, completate: done, mancate: missed,
      rimanenti: total - done - missed, prossima_idx: next < 0 ? null : next,
      percentuale: total ? Math.round((done + missed) / total * 100) : 0};
    return data;
  }

  const api = {create, isRetryable, overlay};
  if(typeof module !== 'undefined' && module.exports) module.exports = api;
  root.GFDriverOutbox = api;
})(typeof window !== 'undefined' ? window : globalThis);
