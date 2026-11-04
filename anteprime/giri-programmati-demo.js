// Dati di esempio e disegno delle tre anteprime di «Giri programmati».
// Solo per il confronto: la pagina vera resta in static/dashboard/js/core.js.
(function(){
  const TODAY = '2026-11-04';
  const DAYS = ['2026-11-02','2026-11-03','2026-11-04','2026-11-05','2026-11-06','2026-11-07','2026-11-08'];
  const SHORT = ['Lun','Mar','Mer','Gio','Ven','Sab','Dom'];
  const LONG = ['Lunedì 2 novembre','Martedì 3 novembre','Mercoledì 4 novembre','Giovedì 5 novembre','Venerdì 6 novembre','Sabato 7 novembre','Domenica 8 novembre'];
  const DRIVERS = ['Marco Esposito','Autista Prova','Antonio Russo','alessandro paglietta','Giuseppe Ferrara','Luca Romano','Sara Siviglia'];
  const R = (day, start, end, driver, vehicle, plate, stops, km, drive, cost, cancelled) =>
    ({day, start, end, driver, vehicle, plate, stops, km, drive, cost, cancelled: !!cancelled});
  const ROUTES = [
    R(0,'07:00','11:20','Sara Siviglia','Fiat Ducato 3','GH 412 KL',9,61.2,'3 h 12 min',13.40,1),
    R(0,'07:00','14:05','Autista Prova','Ford Transit 1','FT 201 AB',12,80.4,'6 h 40 min',17.60,1),
    R(0,'07:00','15:10','alessandro paglietta','Fiat Ducato 1','FD 118 CE',16,241.9,'8 h 02 min',52.30,1),
    R(2,'07:00','10:52','Marco Esposito','Ford Transit 2','FT 202 AB',11,70.1,'3 h 52 min',15.30),
    R(2,'07:00','11:35','Antonio Russo','Fiat Ducato 2','FD 119 CE',13,77.8,'4 h 35 min',16.90),
    R(2,'07:00','12:10','Giuseppe Ferrara','Iveco Daily','ID 330 MN',15,92.4,'5 h 10 min',20.10),
    R(2,'08:00','13:30','Luca Romano','Ford Transit 1','FT 201 AB',12,66.5,'5 h 30 min',14.50),
    R(3,'08:00','12:40','Marco Esposito','Ford Transit 2','FT 202 AB',10,68.2,'4 h 40 min',14.90),
    R(3,'08:00','13:15','Giuseppe Ferrara','Iveco Daily','ID 330 MN',14,88.0,'5 h 15 min',19.10),
    R(3,'08:00','14:02','Luca Romano','Fiat Ducato 2','FD 119 CE',13,74.6,'6 h 02 min',16.30),
    R(3,'09:00','15:20','Autista Prova','Ford Transit 1','FT 201 AB',15,95.1,'6 h 20 min',20.70),
    R(4,'07:00','10:44','Marco Esposito','Ford Transit 2','FT 202 AB',10,73.7,'3 h 44 min',15.97),
    R(4,'07:00','15:30','Autista Prova','Ford Transit 1','FT 201 AB',13,85.62,'8 h 30 min',18.55),
    R(4,'07:00','11:01','Antonio Russo','Fiat Ducato 2','FD 119 CE',14,79.39,'4 h 01 min',17.20),
    R(4,'07:00','15:24','alessandro paglietta','Fiat Ducato 1','FD 118 CE',17,263.72,'8 h 24 min',57.15),
    R(4,'08:00','12:30','Giuseppe Ferrara','Iveco Daily','ID 330 MN',12,70.2,'4 h 30 min',15.20,1),
    R(4,'08:00','13:10','Luca Romano','Fiat Ducato 3','GH 412 KL',11,66.0,'5 h 10 min',14.30,1),
    R(4,'09:00','12:45','Sara Siviglia','Ford Transit 3','FT 203 AB',8,52.8,'3 h 45 min',11.60,1),
  ];
  const LIMIT = 3;
  let selected = 4;

  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const money = v => '€ ' + v.toLocaleString('it-IT',{minimumFractionDigits:2,maximumFractionDigits:2});
  const km = v => v.toLocaleString('it-IT',{maximumFractionDigits:2}) + ' km';
  const initials = n => n.split(/\s+/).map(p => p[0]).join('').slice(0,2).toUpperCase();
  const tone = n => (DRIVERS.indexOf(n) % 6) + 1;
  const short = n => { const [f, ...r] = n.split(/\s+/); return r.length ? `${f[0]}. ${r.join(' ')}` : f; };
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const ofDay = i => ROUTES.filter(r => r.day === i).sort((a,b) => a.cancelled - b.cancelled || a.start.localeCompare(b.start));
  const active = list => list.filter(r => !r.cancelled);
  const avatar = n => `<span class="gf-avatar" data-tone="${tone(n)}" aria-hidden="true">${esc(initials(n))}</span>`;

  // Riepilogo della settimana accanto al titolo
  function weekSummary(){
    const act = active(ROUTES), cancelled = ROUTES.length - act.length;
    const drivers = new Set(act.map(r => r.driver)).size;
    return `${plural(act.length,'giro programmato','giri programmati')} · ${plural(cancelled,'annullato','annullati')} · ${plural(drivers,'autista','autisti')}`;
  }

  // Tabella del giorno scelto, uguale nelle tre varianti
  function dayPanel(withStats){
    const list = ofDay(selected), act = active(list);
    const stops = act.reduce((s,r) => s + r.stops, 0);
    const meta = [act.length ? `${plural(act.length,'giro','giri')} · ${plural(stops,'fermata','fermate')}` : '', list.length - act.length ? plural(list.length - act.length,'annullato','annullati') : ''].filter(Boolean).join(' · ');
    const rows = list.map(r => `<tr${r.cancelled ? ' data-status="danger"' : ''}>
      <td data-label="Orario"><strong>${r.start} – ${r.end}</strong></td>
      <td data-label="Autista"><div class="gf-cluster">${avatar(r.driver)}<span>${esc(r.driver)}</span></div></td>
      <td data-label="Mezzo"><span class="gf-list-item__main"><strong>${esc(r.vehicle)}</strong><small>${esc(r.plate)}</small></span></td>
      <td data-label="Fermate">${r.stops}</td>
      <td data-label="Km previsti">${km(r.km)}</td>
      <td data-label="Guida">${r.drive}</td>
      <td data-label="Costo stimato">${money(r.cost)}</td>
      <td data-label="Azioni"><div class="gf-cluster">${r.cancelled ? '<span class="gf-badge" data-status="danger">Annullato</span>' : ''}<button type="button" class="gf-button" data-variant="secondary" data-size="sm">Apri giro</button></div></td>
    </tr>`).join('');
    const stats = withStats && act.length ? `<div class="gf-panel__body"><div class="gf-stat-strip" data-icons="side" data-fit>
        ${stat('1','M6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M18 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M8 17h6a3 3 0 0 0 0-6h-4a3 3 0 0 1 0-6h6','Giri',act.length,'programmati')}
        ${stat('2','M12 21s-7-6.5-7-12a7 7 0 0 1 14 0c0 5.5-7 12-7 12z M12 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4z','Fermate',stops,'da consegnare')}
        ${stat('3','M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3 2','Km previsti',Math.round(act.reduce((s,r)=>s+r.km,0)).toLocaleString('it-IT'),'km')}
        ${stat('6','M17 6.5A7 7 0 1 0 17 17.5 M4 10h10 M4 14h10','Costo stimato',money(act.reduce((s,r)=>s+r.cost,0)),'carburante')}
      </div></div>` : '';
    const body = list.length
      ? `${stats}<div class="gf-table-wrap"><table class="gf-table" data-gf-responsive="cards">
          <thead><tr><th scope="col">Orario</th><th scope="col">Autista</th><th scope="col">Mezzo</th><th scope="col">Fermate</th><th scope="col">Km previsti</th><th scope="col">Guida</th><th scope="col">Costo stimato</th><th scope="col"><span class="gf-muted">Azioni</span></th></tr></thead>
          <tbody>${rows}</tbody></table></div>`
      : `<div class="gf-empty"><h3 class="gf-subtitle">Nessun giro programmato</h3><p>In questa giornata non ci sono giri assegnati.</p><button type="button" class="gf-button" data-variant="secondary">Pianifica un giro</button></div>`;
    return `<section class="gf-panel" aria-labelledby="dayTitle">
      <header class="gf-panel__header"><h2 class="gf-panel__title" id="dayTitle">${LONG[selected]}${DAYS[selected] === TODAY ? ' <span class="gf-badge" data-status="neutral">Oggi</span>' : ''}</h2><span class="gf-panel__meta">${meta}</span></header>
      ${body}
    </section>`;
  }
  function stat(t, path, label, value, unit){
    return `<div class="gf-stat-strip__cell"><span class="gf-stat-strip__icon" data-tone="${t}" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="${path}"/></svg></span><span class="gf-stat-strip__label">${label}</span><strong class="gf-stat-strip__value">${value}</strong><small class="gf-stat-strip__unit">${unit}</small></div>`;
  }
  const dayName = i => `${SHORT[i]}${DAYS[i] === TODAY ? ' · oggi' : ''}`;

  // Tre varianti della C: giri con orario, autista, mezzo e fermate; «Mostra di più» in fondo;
  // nei giorni vuoti da oggi in poi icona e «Pianifica giro», nei giorni passati solo «Nessun giro».
  // A · «Mostra altri N» in fondo, contando giri nascosti e annullati; niente annullati in colonna.
  // B · «Mostra di più» in fondo a ogni giorno con giri; annullati come badge accanto al conteggio.
  // C · «Mostra altri N» in fondo solo se servono; annullati non in colonna (solo nella tabella sotto);
  //     giorno vuoto nel riquadro tratteggiato.
  const CAL_ICON = '<span class="gf-empty__icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 5h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M16 3v4 M8 3v4 M4 11h16"/></svg></span>';
  function weekCols(v){
    return `<div class="gf-grid" data-cols="7">${DAYS.map((iso, i) => {
      const list = active(ofDay(i)), count = list.length, cancelled = ofDay(i).length - count;
      const on = i === selected, hidden = list.length - LIMIT, future = iso >= TODAY;
      const item = r => `<button type="button" class="gf-list-item" data-pick="${i}" title="${esc(`${r.start} · ${r.driver} · ${r.vehicle} · ${r.stops} fermate`)}"><span class="gf-list-item__main"><strong>${r.start} · ${esc(short(r.driver))}</strong><small>${esc(r.vehicle)}</small><small>${plural(r.stops,'fermata','fermate')}</small></span></button>`;
      let items;
      if(count) items = list.slice(0, LIMIT).map(item).join('');
      else {
        const plan = future ? `<button type="button" class="gf-button" data-variant="${v === 'B' ? 'secondary' : 'link'}" data-size="sm">Pianifica giro</button>` : '';
        const empty = `${CAL_ICON}<p>Nessun giro</p>${plan}`;
        items = v === 'C' ? `<div class="gf-panel__body"><div class="gf-day-empty">${empty}</div></div>` : `<div class="gf-empty">${empty}</div>`;
      }
      // A: il numero conta anche gli annullati, che si vedono nella tabella sotto.
      const extra = Math.max(hidden, 0) + (v === 'A' ? cancelled : 0);
      const moreLabel = v === 'B' ? 'Mostra di più' : `Mostra altri ${extra}`;
      const showMore = v === 'B' ? count > 0 : extra > 0;
      const left = '';
      const footer = showMore || left
        ? `<footer class="gf-panel__footer">${left}${showMore ? `<button type="button" class="gf-button" data-variant="link" data-size="sm" data-pick="${i}">${moreLabel}</button>` : ''}</footer>` : '';
      const badge = count ? `<span class="gf-badge" data-status="${on ? 'info' : 'neutral'}">${plural(count,'giro','giri')}</span>` : '';
      const cancelledBadge = v === 'B' && cancelled ? `<span class="gf-badge" data-status="danger">${cancelled} annull.</span>` : '';
      const weekend = i > 4 ? ' data-day="weekend"' : '';
      return `<section class="gf-panel"${weekend} aria-label="${LONG[i]}">
        <header class="gf-panel__header"><button type="button" class="gf-day-head" aria-pressed="${on}" data-pick="${i}"><span class="gf-day-head__weekday">${dayName(i)}</span><span class="gf-day-head__number">${iso.slice(8).replace(/^0/,'')}</span>${badge || cancelledBadge}</button></header>
        <div class="gf-list">${items}</div>${footer}
      </section>`;
    }).join('')}</div>`;
  }

  function render(){
    const v = document.body.dataset.demoVariant;
    const week = weekCols(v);
    document.querySelector('[data-demo-summary]').textContent = weekSummary();
    document.querySelector('[data-demo-week]').innerHTML = week;
    document.querySelector('[data-demo-day]').innerHTML = dayPanel(false);
  }
  document.addEventListener('click', e => {
    const pick = e.target.closest('[data-pick]');
    if(pick){ selected = Number(pick.dataset.pick); render(); return; }
    if(e.target.closest('[data-demo-today]')){ selected = DAYS.indexOf(TODAY); render(); }
  });
  document.addEventListener('DOMContentLoaded', render);
})();
