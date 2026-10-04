/* Shared customer-link controls for company desktop and mobile portals. */
function trackingButton(delivery, route) {
  if (!delivery?.id || route?.status === 'bozza') return '';
  return `<button type="button" class="btn-secondary mini-btn customer-tracking-trigger" onclick="openCustomerTracking(${Number(delivery.id)})">Tracking cliente</button>`;
}

async function openCustomerTracking(deliveryId) {
  document.getElementById('customerTrackingDialog')?.remove();
  const dialog = document.createElement('dialog');
  dialog.id = 'customerTrackingDialog';
  dialog.className = 'customer-tracking-dialog';
  dialog.setAttribute('aria-labelledby', 'customerTrackingTitle');
  dialog.innerHTML = `<div class="tracking-dialog-header">
    <span class="tracking-dialog-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2"/></svg></span>
    <div><p class="tracking-eyebrow">INFORMAZIONI DI CONSEGNA</p><h2 id="customerTrackingTitle">Tracking cliente</h2></div>
    </div>
    <div class="tracking-dialog-body">
      <p class="tracking-intro">Tieni aggiornato il destinatario, con un solo link.</p>
      <div class="tracking-privacy"><strong>Una pagina dedicata alla sua consegna</strong><p>Chi riceve il link può consultare solo lo stato e gli orari di questa consegna, senza accedere al gestionale.</p></div>
      <label for="customerTrackingUrl">Link della consegna</label>
      <input id="customerTrackingUrl" readonly type="text" autocomplete="off" placeholder="Preparazione del link…" aria-describedby="customerTrackingExpiry">
      <p id="customerTrackingExpiry" class="tracking-expiry"></p>
      <div class="tracking-actions"><button type="button" data-action="copy" disabled>Copia link</button>
        <button type="button" data-action="share" disabled>Condividi</button>
        <button type="button" data-action="open" disabled>Apri pagina</button></div>
      <p class="tracking-warning"><strong>Hai ricalcolato il giro?</strong> I link precedenti non saranno più validi: condividi quelli nuovi.</p>
      <p id="customerTrackingMessage" role="status" aria-live="polite">Caricamento…</p>
    </div>
    <div class="tracking-dialog-footer"><button type="button" data-action="revoke" disabled>Revoca link</button>
      <button type="button" data-action="close" autofocus>Chiudi</button></div>`;
  document.body.appendChild(dialog);
  dialog.showModal();
  const field = dialog.querySelector('input');
  const message = dialog.querySelector('#customerTrackingMessage');
  let url = '';
  const controls = [...dialog.querySelectorAll('[data-action]')];
  const enable = enabled => controls.forEach(button => { if (button.dataset.action !== 'close') button.disabled = !enabled; });
  async function request(method) {
    const response = await fetch(`/api/deliveries/${deliveryId}/tracking`, {method, credentials:'same-origin', cache:'no-store'});
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || 'Operazione non disponibile');
    return body;
  }
  controls.forEach(button => button.addEventListener('click', async () => {
    const action = button.dataset.action;
    try {
      if (action === 'close') { dialog.close(); dialog.remove(); return; }
      if (action === 'copy') {
        try { await navigator.clipboard.writeText(url); message.textContent = 'Link copiato.'; }
        catch (_) { field.focus(); field.select(); message.textContent = 'Seleziona e copia il link qui sopra.'; }
      }
      if (action === 'share') {
        if (navigator.share) await navigator.share({title:'La tua consegna', text:'Segui la tua consegna su GiroFacile', url});
        else { field.focus(); field.select(); message.textContent = 'Copia il link e incollalo nel messaggio al cliente.'; }
      }
      if (action === 'open') window.open(url, '_blank', 'noopener,noreferrer');
      if (action === 'revoke') {
        enable(false);
        await request('DELETE');
        url = ''; field.value = ''; field.placeholder = 'Link revocato';
        dialog.querySelector('#customerTrackingExpiry').textContent = '';
        message.textContent = 'Link revocato. Se la consegna è ancora aperta, chiudi e riapri Tracking cliente per generarne uno nuovo.';
      }
    } catch (error) {
      if (error.name !== 'AbortError') message.textContent = error.message;
      if (url) enable(true);
    }
  }));
  try {
    const data = await request('POST');
    url = data.url;
    field.value = url;
    dialog.querySelector('#customerTrackingExpiry').textContent = `Valido fino al ${new Date(data.expires_at).toLocaleString('it-IT')}.`;
    message.textContent = 'Il link si aggiorna con gli stati registrati dall’autista.';
    enable(true);
  } catch (error) { message.textContent = error.message; }
}
