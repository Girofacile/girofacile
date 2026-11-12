/* Avvisi della piattaforma e pagina di manutenzione (12/11/2026).
   Legge /api/public/status (raggiungibile anche durante la manutenzione) e mostra:
   - gli avvisi con il componente .gf-banner, fisso in basso, uno alla volta (landing, accesso, gestionale e portali);
   - durante la manutenzione una finestra .gf-modal che non si chiude, ricaricata da sola a lavori finiti.
   Un avviso chiuso resta chiuso nella sessione; quello di manutenzione ricompare nell'ultima mezz'ora. */
(function(){
  'use strict';
  var URL_STATUS = '/api/public/status';
  var POLL = 60000, POLL_MAINTENANCE = 30000, KEY = 'gf-notice-closed:';
  var ICONS = {
    maintenance: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>'
  };
  var last = null, timer = null, dialog = null, wasMaintenance = false;

  function esc(value){
    return String(value == null ? '' : value).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function read(id){ try { return sessionStorage.getItem(KEY + id); } catch(e) { return null; } }
  function write(id, value){ try { sessionStorage.setItem(KEY + id, value); } catch(e) {} }
  function reminding(notice){ return !!notice.remind_at && new Date(notice.remind_at) <= new Date(); }
  function visible(notice){
    var closed = read(notice.id);
    if(!closed) return true;
    return closed === 'early' && reminding(notice);
  }
  function icon(kind){
    return '<span class="gf-banner__icon" aria-hidden="true"><svg viewBox="0 0 24 24">' + (ICONS[kind] || ICONS.info) + '</svg></span>';
  }
  function banner(notice){
    var el = document.createElement('div');
    el.className = 'gf-banner';
    el.dataset.gfNotice = notice.id;
    el.setAttribute('role', 'region');
    el.setAttribute('aria-label', notice.title || 'Avviso');
    el.innerHTML = icon(notice.kind) + '<div class="gf-banner__text"><strong>' + esc(notice.title) + '</strong><p>' + esc(notice.text) + '</p></div>'
      + '<button class="gf-button" data-variant="ghost" data-size="sm" type="button" aria-label="Chiudi avviso">✕</button>';
    el.querySelector('button').addEventListener('click', function(){
      write(notice.id, reminding(notice) ? 'late' : 'early');
      render();
    });
    return el;
  }
  // Un altro banner fisso in basso (es. cookie) ha la precedenza: l'avviso compare quando si chiude.
  function otherBannerOpen(){
    return Array.prototype.some.call(document.querySelectorAll('.gf-banner:not([data-gf-notice]):not([data-embedded])'), function(el){
      return !el.hidden && getComputedStyle(el).display !== 'none';
    });
  }
  function host(){
    var box = document.getElementById('gf-platform-notices');
    if(!box){
      box = document.createElement('div');
      box.id = 'gf-platform-notices';
      document.body.appendChild(box);
    }
    return box;
  }
  function renderNotices(notices){
    var box = host();
    box.replaceChildren();
    // Uno alla volta (la manutenzione ha la precedenza), mai sopra il banner dei cookie.
    var shown = otherBannerOpen() ? [] : (notices || []).filter(visible).slice(0, 1);
    shown.forEach(function(notice){ box.appendChild(banner(notice)); });
  }
  function renderMaintenance(info){
    if(!info){
      if(dialog){ dialog.close(); dialog.remove(); dialog = null; }
      return;
    }
    if(!dialog){
      dialog = document.createElement('dialog');
      dialog.className = 'gf-modal';
      dialog.setAttribute('aria-labelledby', 'gf-maintenance-title');
      // La pagina di manutenzione non si chiude con Esc: si chiude da sola a lavori finiti.
      dialog.addEventListener('cancel', function(event){ event.preventDefault(); });
      document.body.appendChild(dialog);
    }
    var when = info.until_label ? 'GiroFacile tornerà disponibile ' + esc(info.until_label) + ' circa.' : 'GiroFacile tornerà disponibile al termine dei lavori.';
    dialog.innerHTML = '<div class="gf-modal__body"><div class="gf-empty">'
      + '<span class="gf-empty__icon" aria-hidden="true"><svg viewBox="0 0 24 24">' + ICONS.maintenance + '</svg></span>'
      + '<h2 id="gf-maintenance-title">Siamo in manutenzione</h2>'
      + '<p>' + when + '</p>'
      + (info.message ? '<p>' + esc(info.message) + '</p>' : '')
      + '<p class="gf-muted">I tuoi dati sono al sicuro. Questa pagina si aggiorna da sola.</p>'
      + '</div></div>';
    if(!dialog.open){ try { dialog.showModal(); } catch(e) { dialog.setAttribute('open', ''); } }
  }
  function render(){
    if(!last) return;
    renderMaintenance(last.maintenance);
    renderNotices(last.maintenance ? [] : last.notices);
  }
  function schedule(delay){
    clearTimeout(timer);
    timer = setTimeout(refresh, delay);
  }
  function refresh(){
    fetch(URL_STATUS, {credentials: 'same-origin', cache: 'no-store'})
      .then(function(response){ return response.ok ? response.json() : null; })
      .then(function(data){
        if(!data) return schedule(POLL);
        var active = !!data.maintenance;
        last = data;
        // A lavori finiti si ricarica la pagina, così ogni dato torna aggiornato.
        if(wasMaintenance && !active){ location.reload(); return; }
        wasMaintenance = active;
        render();
        schedule(active ? POLL_MAINTENANCE : POLL);
      })
      .catch(function(){ schedule(POLL); });
  }
  // Chiudendo il banner dei cookie l'avviso può comparire subito.
  document.addEventListener('click', function(){ if(last && !last.maintenance) setTimeout(render, 300); });
  document.addEventListener('visibilitychange', function(){ if(document.visibilityState === 'visible') refresh(); });
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', refresh);
  else refresh();
})();
