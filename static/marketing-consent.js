/* Consenso ai cookie di marketing e pixel di Meta (23/11/2026, finestra centrale 26/11/2026).
 *
 * Il pixel parte SOLO dopo «Accetta». Nessuna scelta salvata: sulle pagine pubbliche compare una
 * finestra al centro dello schermo che blocca la pagina finché non si sceglie «Accetta» o «Rifiuta»
 * (niente X, Esc non la chiude). «Rifiuta» resta sempre disponibile e il sito funziona lo stesso.
 * Con data-gf-consent="passive" sullo <script> (pagina di accesso/area riservata) la finestra non compare
 * e non si registra la visita, tranne l'arrivo dopo l'iscrizione (/dashboard?registrazione=ok):
 * per chi ha accettato si registra quella visita, usata dalla conversione personalizzata di Meta.
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

  const SIGNUP_PARAM = 'registrazione';

  function closeBanner(){
    const box = document.getElementById('gfConsentBanner');
    if(!box) return;
    box.dataset.chosen = '1';
    if(box.open) box.close();
    box.remove();
  }
  function choose(value){
    write(value);
    closeBanner();
    if(value === 'accepted'){ loadPixel(); window.fbq('track', 'PageView'); }
  }
  function showBanner(){
    if(document.getElementById('gfConsentBanner')) return;
    const box = document.createElement('dialog');
    box.id = 'gfConsentBanner';
    box.className = 'gf-modal';
    box.setAttribute('aria-labelledby', 'gfConsentTitle');
    box.setAttribute('aria-describedby', 'gfConsentText');
    box.innerHTML = '<header class="gf-modal__header"><div><h2 class="gf-modal__title" id="gfConsentTitle">Cookie per la pubblicità</h2>'
      + '<p class="gf-muted">Scegli per continuare sul sito</p></div></header>'
      + '<div class="gf-modal__body gf-stack" id="gfConsentText">'
      + '<p class="gf-text">Con il tuo consenso usiamo il pixel di Meta per misurare le visite e capire quali campagne pubblicitarie '
      + 'portano nuovi clienti su GiroFacile.</p>'
      + '<p class="gf-text">Se rifiuti il sito funziona lo stesso. Puoi cambiare idea quando vuoi da «Preferenze cookie» in fondo alla pagina. '
      + '<a href="/cookie-policy">Cookie Policy</a></p></div>'
      + '<footer class="gf-modal__footer"><button type="button" class="gf-button" data-variant="secondary" data-consent="rejected">Rifiuta</button>'
      + '<button type="button" class="gf-button" data-variant="primary" data-consent="accepted">Accetta</button></footer>';
    box.addEventListener('click', event => {
      const button = event.target.closest('[data-consent]');
      if(button) choose(button.dataset.consent);
    });
    // Senza una scelta la finestra non si chiude: Esc viene ignorato e, se il browser la chiude lo stesso, si riapre.
    box.addEventListener('cancel', event => event.preventDefault());
    box.addEventListener('close', () => {
      if(!box.dataset.chosen && box.isConnected) setTimeout(() => { if(!box.dataset.chosen && box.isConnected && !box.open) box.showModal(); }, 0);
    });
    document.body.appendChild(box);
    box.showModal();
  }

  // Arrivo dopo l'iscrizione: la visita a /dashboard?registrazione=ok va a Meta (solo con il consenso),
  // poi il tag sparisce dall'indirizzo, così un ricaricamento non conta una seconda iscrizione.
  function signupLanding(){
    const params = new URLSearchParams(location.search);
    if(!params.has(SIGNUP_PARAM)) return false;
    const clean = () => {
      const url = new URL(location.href);
      url.searchParams.delete(SIGNUP_PARAM);
      history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    };
    if(read() === 'accepted'){
      loadPixel().then(() => setTimeout(clean, 1500));
      window.fbq('track', 'PageView');
    } else clean();
    return true;
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
    if(passive){ signupLanding(); return; }
    if(choice === 'accepted'){ loadPixel(); window.fbq('track', 'PageView'); }
    else if(!choice) showBanner();
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
