/* Esiti dell'autista in attesa di rete.
 * Se l'invio fallisce per rete assente o server momentaneamente non raggiungibile,
 * l'esito resta sul telefono e parte appena la connessione torna. Il server accetta
 * le ripetizioni dello stesso esito, quindi un invio doppio non crea duplicati. */
(function(root){
  'use strict';
  // Errori temporanei: l'esito resta in coda. Gli errori 5xx del server sono sempre temporanei:
  // scartare l'esito per un 500 farebbe perdere una consegna fatta.
  const RETRY_STATUSES = new Set([0, 401, 408, 425, 429]);

  function create({storage, send, key, onChange, locks}={}){
    let items = [];
    let flushing = null;
    let sequence = 0;
    // Esiti che non è stato possibile scrivere sul telefono (memoria piena): restano in questa pagina.
    let unsaved = [];
    const lockManager = locks === undefined ? (root.navigator && root.navigator.locks) : locks;
    const changed = () => { if(onChange) onChange(items.slice()); };
    // Ogni operazione ha un identificativo proprio: dopo l'invio si toglie solo quella confermata,
    // anche se nel frattempo un nuovo esito della stessa consegna è entrato in coda.
    const newOpId = () => Date.now().toString(36) + '-' + (++sequence).toString(36) + '-' + Math.random().toString(36).slice(2, 8);

    // Esiti già inviati in questa pagina: se il telefono non riesce a salvarne la rimozione,
    // non vengono comunque rimandati.
    const sent = new Set();
    // Ogni esito ha una voce propria sul telefono (key + ':' + opId). Togliere un esito inviato
    // è quindi una semplice cancellazione, che riesce anche a telefono pieno: riaprendo il
    // portale l'esito confermato non riparte. La lista unica sotto «key» è della versione precedente.
    const prefix = key + ':';
    let legacyIds = new Set();

    function storedKeys(){
      const keys = [];
      try { for(let i = 0; i < storage.length; i++){ const k = storage.key(i); if(k && k.startsWith(prefix)) keys.push(k); } }
      catch(e) {}
      return keys;
    }
    function readLegacy(){
      let stored;
      try { stored = JSON.parse(storage?.getItem(key) || '[]'); }
      catch(e) { stored = []; }
      if(!Array.isArray(stored)) stored = [];
      // Esiti della versione precedente, senza identificativo: ne ricevono uno ricavato dal contenuto,
      // uguale a ogni lettura e in ogni scheda, così l'esito inviato si riconosce e si toglie.
      return stored.filter(Boolean).map(item => item.opId ? item : {...item, opId: legacyOpId(item)});
    }
    function readStored(){
      if(!storage) return [];
      const byId = new Map();
      const legacy = readLegacy();
      legacyIds = new Set(legacy.map(x => x.opId));
      for(const item of legacy) byId.set(item.opId, item);
      for(const k of storedKeys()){
        try { const item = JSON.parse(storage.getItem(k)); if(item && item.opId){ byId.set(item.opId, item); legacyIds.delete(item.opId); } }
        catch(e) {}
      }
      return [...byId.values()];
    }
    const byQueue = (a, b) => String(a.queuedAt || '').localeCompare(String(b.queuedAt || '')) || (a.order || 0) - (b.order || 0);
    // Il telefono è la fonte comune a tutte le schede: si rilegge sempre prima di modificare,
    // così una seconda scheda aperta non cancella gli esiti salvati dalla prima.
    function load(){
      const stored = readStored();
      const known = new Set(stored.map(x => x.opId));
      items = stored.concat(unsaved.filter(x => !known.has(x.opId))).filter(x => !sent.has(x.opId)).sort(byQueue);
    }
    function persist(item){
      if(!storage) return false;
      try { storage.setItem(prefix + item.opId, JSON.stringify(item)); return true; }
      catch(e) { return false; }
    }
    function forget(opId){
      if(!storage) return;
      if(legacyIds.has(opId)){
        const rest = readLegacy().filter(x => x.opId !== opId);
        try { if(rest.length) storage.setItem(key, JSON.stringify(rest)); else storage.removeItem(key); }
        catch(e) {}
        return;
      }
      try { storage.removeItem(prefix + opId); } catch(e) {}
    }
    function update(change){
      load();
      const before = new Map(items.map(x => [x.opId, x]));
      const after = change(items);
      const kept = new Set(after.map(x => x.opId));
      let persisted = true;
      for(const opId of before.keys()) if(!kept.has(opId)){ forget(opId); unsaved = unsaved.filter(x => x.opId !== opId); }
      for(const item of after) if(!before.has(item.opId) && !persist(item)){ persisted = false; unsaved.push(item); }
      items = after;
      changed();
      return persisted;
    }
    // Gli esiti della versione precedente passano a voci separate; la vecchia lista si toglie
    // solo quando tutti sono stati copiati.
    function migrate(){
      const legacy = readLegacy();
      if(!legacy.length || !legacy.every(persist)) return;
      try { storage.removeItem(key); legacyIds = new Set(); } catch(e) {}
    }

    function add(item){
      // Un nuovo esito per la stessa consegna e azione sostituisce quello precedente.
      const entry = {...item, opId: newOpId(), queuedAt: item.queuedAt || new Date().toISOString(), order: Date.now() * 1000 + (sequence % 1000)};
      return update(list => list.filter(x => !(x.deliveryId === item.deliveryId && x.kind === item.kind)).concat(entry));
    }

    function pending(routeId){
      load();
      return items.filter(x => routeId == null || Number(x.routeId) === Number(routeId));
    }

    // Invia in ordine; si ferma al primo errore temporaneo per non saltare esiti.
    async function drain(){
      const rejected = [];
      for(;;){
        load();
        const item = items[0];
        if(!item) break;
        try { await send(item); }
        catch(e) {
          if(isRetryable(e)) break;
          rejected.push({item, message: e.message});
        }
        // Si toglie l'operazione appena inviata, non «la prima»: potrebbe essere stata sostituita.
        update(list => list.filter(x => x.opId !== item.opId));
        sent.add(item.opId);
      }
      return rejected;
    }

    function flush(){
      if(flushing) return flushing;
      // Una sola scheda alla volta invia gli esiti: le altre aspettano il proprio turno.
      const run = lockManager && typeof lockManager.request === 'function'
        ? lockManager.request(key + ':invio', drain)
        : drain();
      flushing = Promise.resolve(run).finally(() => { flushing = null; });
      return flushing;
    }

    // Un'altra scheda ha cambiato la coda: si aggiorna il conteggio mostrato.
    function refresh(){ load(); changed(); }

    if(storage) migrate();
    load();
    return {add, pending, flush, refresh, count: () => { load(); return items.length; }};
  }

  function legacyOpId(item){
    const text = JSON.stringify([item.kind, item.deliveryId, item.routeId, item.url, item.queuedAt, item.body]);
    let hash = 5381;
    for(let i = 0; i < text.length; i++) hash = ((hash * 33) ^ text.charCodeAt(i)) >>> 0;
    return 'legacy-' + hash.toString(36);
  }

  function isRetryable(error){
    const status = Number(error && error.status);
    return !!error && (error.offline === true || RETRY_STATUSES.has(status) || (status >= 500 && status <= 599));
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
