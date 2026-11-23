/* Consenso ai cookie di marketing e pixel di Meta (23/11/2026).
 *
 * Il pixel parte SOLO dopo «Accetta». Nessuna scelta salvata: si mostra il banner (pagine pubbliche).
 * Con data-gf-consent="passive" sullo <script> (pagina di accesso/area riservata) il banner non compare
 * e non si registra la visita: si invia solo un evento esplicito (es. registrazione completata)
 * a chi ha già accettato sul sito pubblico.
 */
(function(){
  'use strict';
  const PIXEL_ID = '1444449421091767';
  const KEY = 'gf_cookie_consent';
  const script = document.currentScript;
  const passive = script?.dataset.gfConsent === 'passive';
  let loaded = null;

  function read(){ try { return localStorage.getItem(KEY); } catch(_e) { return null; } }
  function write(value){ try { localStorage.setItem(KEY, value); } catch(_e) {} }

  // Codice ufficiale di Meta, caricato solo dopo il consenso.
  function loadPixel(){
    if(loaded) return loaded;
    loaded = new Promise(resolve => {
      !function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
        n.callMethod.apply(n,arguments):n.queue.push(arguments)};
        if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
        n.queue=[];t=b.createElement(e);t.async=!0;
        t.src=v;t.onload=resolve;t.onerror=resolve;s=b.getElementsByTagName(e)[0];
        s.parentNode.insertBefore(t,s)}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');
      window.fbq('init', PIXEL_ID);
    });
    return loaded;
  }

  function closeBanner(){ document.getElementById('gfConsentBanner')?.remove(); }
  function choose(value){
    write(value);
    closeBanner();
    if(value === 'accepted'){ loadPixel(); window.fbq('track', 'PageView'); }
  }
  function showBanner(){
    if(document.getElementById('gfConsentBanner')) return;
    const box = document.createElement('div');
    box.id = 'gfConsentBanner';
    box.className = 'gf-banner';
    box.setAttribute('role', 'region');
    box.setAttribute('aria-label', 'Consenso ai cookie');
    box.innerHTML = '<span class="gf-banner__icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3a9 9 0 1 0 9 9 4 4 0 0 1-5-5 4 4 0 0 1-4-4z M8.5 11.5h.01 M12 16h.01 M15.5 13.5h.01"/></svg></span>'
      + '<div class="gf-banner__text"><strong>Cookie per la pubblicità</strong><p>Con il tuo consenso usiamo il pixel di Meta per misurare visite e campagne pubblicitarie. '
      + 'Se rifiuti il sito funziona lo stesso. <a href="/cookie-policy">Cookie Policy</a></p></div>'
      + '<div class="gf-cluster"><button type="button" class="gf-button" data-variant="secondary" data-size="sm" data-consent="rejected">Rifiuta</button>'
      + '<button type="button" class="gf-button" data-variant="primary" data-size="sm" data-consent="accepted">Accetta</button></div>';
    box.addEventListener('click', event => {
      const button = event.target.closest('[data-consent]');
      if(button) choose(button.dataset.consent);
    });
    document.body.appendChild(box);
  }

  window.GFMarketing = {
    // Evento esplicito (es. CompleteRegistration): parte solo con il consenso; al massimo 1 secondo di attesa.
    track(event, params){
      if(read() !== 'accepted') return Promise.resolve(false);
      const ready = loadPixel().then(() => { window.fbq('track', event, params || {}); return true; });
      return Promise.race([ready, new Promise(resolve => setTimeout(() => resolve(false), 1000))]);
    },
    // «Preferenze cookie» nel piè di pagina: si può cambiare idea in qualsiasi momento.
    openPreferences(){ showBanner(); },
    consent: read
  };

  function start(){
    const choice = read();
    if(choice === 'accepted' && !passive){ loadPixel(); window.fbq('track', 'PageView'); }
    else if(!choice && !passive) showBanner();
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
