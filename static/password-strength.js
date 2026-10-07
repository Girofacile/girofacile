(function(root){
  "use strict";

  const COMMON = new Set([
    "password","password1","password123","password2026",
    "admin","admin123","admin2026","administrator",
    "girofacile","girofacile123","girofacile2026",
    "12345678","123456789","1234567890","qwerty","qwerty123",
    "abcdefghi","letmein","welcome","benvenuto","changeme"
  ]);
  const SEQUENCES = ["123456","654321","abcdef","fedcba","qwerty","asdfgh","zxcvbn","qazwsx"];

  function compact(value){
    return String(value || "").normalize("NFKD").replace(/[\u0300-\u036f]/g,"").toLowerCase().replace(/[^a-z0-9]/g,"");
  }

  function contextTerms(values){
    const out = new Set();
    (values || []).forEach(function(value){
      const raw = String(value || "").trim();
      if(!raw) return;
      const all = compact(raw);
      if(all.length >= 6) out.add(all);
      raw.split(/[^A-Za-zÀ-ÖØ-öø-ÿ0-9]+/).forEach(function(token){
        const clean = compact(token);
        if(clean.length >= 4) out.add(clean);
      });
    });
    return Array.from(out);
  }

  function assess(password, context){
    const p = String(password || "");
    const c = compact(p);
    const checks = {
      length: p.length >= 8,
      uppercase: /[A-ZÀ-ÖØ-Þ]/.test(p),
      lowercase: /[a-zà-öø-ÿ]/.test(p),
      special: /[^A-Za-zÀ-ÖØ-öø-ÿ0-9\s]/.test(p),
      no_outer_spaces: p.trim() === p
    };
    const risks = [];
    const commonPattern = /^(password|admin|utente|user|azienda)\d{0,6}$/.test(c);
    if(COMMON.has(c) || commonPattern || c.indexOf("girofacile") >= 0 || c.indexOf("qwerty") >= 0) risks.push("common");
    if(SEQUENCES.some(function(sequence){ return c.indexOf(sequence) >= 0; })) risks.push("sequence");
    if(/(.)\1{3,}/i.test(p) || /(.{2,4})\1{2,}/i.test(p)) risks.push("repeated");
    if(c && contextTerms(context).some(function(term){ return c.indexOf(term) >= 0; })) risks.push("context");

    let points = 0;
    if(checks.length) points += 1;
    if(checks.uppercase && checks.lowercase) points += 1;
    if(checks.special) points += 1;
    if(/\d/.test(p)) points += 1;
    if(p.length >= 12) points += 1;
    if(p.length >= 16) points += 1;
    if(new Set(p.toLowerCase()).size >= 5) points += 1;

    const hardOk = Object.keys(checks).every(function(key){ return checks[key]; });
    if(risks.length) points = Math.min(points, 1);

    let level="weak", label="Debole";
    if(risks.length){ level="very_weak"; label="Molto debole"; }
    else if(!hardOk || points < 4){ level="weak"; label="Debole"; }
    else if(points >= 6){ level="strong"; label="Forte"; }
    else { level="good"; label="Buona"; }

    const acceptable = hardOk && !risks.length && points >= 4;
    let message = "Password accettabile";
    if(!checks.length) message = "La password deve contenere almeno 8 caratteri";
    else if(!checks.uppercase) message = "La password deve contenere almeno una lettera maiuscola";
    else if(!checks.lowercase) message = "La password deve contenere almeno una lettera minuscola";
    else if(!checks.special) message = "La password deve contenere almeno un carattere speciale";
    else if(!checks.no_outer_spaces) message = "La password non può iniziare o terminare con spazi";
    else if(risks.indexOf("context") >= 0) message = "Non usare nome azienda, username, email o altri dati dell'account";
    else if(risks.indexOf("common") >= 0) message = "Questa password è troppo comune o prevedibile";
    else if(risks.indexOf("sequence") >= 0) message = "Evita sequenze prevedibili come 123456, abcdef o qwerty";
    else if(risks.indexOf("repeated") >= 0) message = "Evita caratteri o gruppi ripetuti troppe volte";
    else if(!acceptable) message = "La password è ancora troppo debole: rendila meno prevedibile";

    return {acceptable:acceptable,level:level,label:label,score:points,checks:checks,risks:risks,message:message};
  }

  function escapeHtml(value){
    return String(value || "").replace(/[&<>"']/g,function(ch){
      return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch];
    });
  }

  function render(target, result){
    if(!target) return;
    const widths={very_weak:18,weak:38,good:72,strong:100};
    target.setAttribute("data-level",result.level);
    target.innerHTML =
      '<div class="gf-password-meter-head"><span>Sicurezza password</span><strong>'+escapeHtml(result.label)+'</strong></div>'+
      '<div class="gf-password-meter-track" aria-hidden="true"><span style="width:'+(widths[result.level] || 0)+'%"></span></div>'+
      '<div class="gf-password-meter-rules">'+
        '<span class="'+(result.checks.length?'ok':'')+'">8+ caratteri</span>'+
        '<span class="'+(result.checks.uppercase?'ok':'')+'">1 maiuscola</span>'+
        '<span class="'+(result.checks.lowercase?'ok':'')+'">1 minuscola</span>'+
        '<span class="'+(result.checks.special?'ok':'')+'">1 carattere speciale</span>'+
      '</div>'+
      '<div class="gf-password-meter-message '+(result.acceptable?'ok':'')+'">'+escapeHtml(result.message)+'</div>';
  }

  const controllers = [];
  function attach(options){
    options = options || {};
    const input = document.getElementById(options.inputId);
    const target = document.getElementById(options.meterId);
    if(!input || !target) return null;
    const confirmInput = options.confirmInputId ? document.getElementById(options.confirmInputId) : null;
    const button = options.buttonId ? document.getElementById(options.buttonId) : null;
    const getContext = typeof options.context === "function" ? options.context : function(){ return options.context || []; };

    function refresh(){
      const result = assess(input.value,getContext());
      render(target,result);
      if(button){
        const confirmOk = !confirmInput || (!!confirmInput.value && confirmInput.value === input.value);
        button.disabled = !(result.acceptable && confirmOk);
      }
      return result;
    }

    input.addEventListener("input",refresh);
    if(confirmInput) confirmInput.addEventListener("input",refresh);
    (options.watchIds || []).forEach(function(id){
      const el=document.getElementById(id);
      if(el) el.addEventListener("input",refresh);
    });
    const controller={refresh:refresh,assess:function(){ return assess(input.value,getContext()); }};
    controllers.push(controller);
    refresh();
    return controller;
  }

  function refreshAll(){ controllers.forEach(function(controller){ controller.refresh(); }); }

  root.GiroFacilePasswordStrength={assess:assess,render:render,attach:attach,refreshAll:refreshAll};
})(window);
