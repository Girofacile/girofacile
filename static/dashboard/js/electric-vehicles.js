/* Electric mobility presentation. Limits and slot allocation come from the server. */
(function(global){
  const escape=value=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const number=value=>value==null?"∞":escape(value);
  function planBenefit(plan){
    const bonus=Number(plan?.electric_vehicle_bonus||0);
    return bonus>0?`⚡ +${bonus} ${bonus===1?"veicolo elettrico":"veicoli elettrici"} bonus`:"";
  }
  function summaryHtml(usage){
    if(!usage) return '<p class="gf-vehicle-usage-note" role="status">Disponibilità degli slot non disponibile. I limiti saranno verificati al salvataggio.</p>';
    const bonus=Number(usage.electric_bonus||0);
    const benefit=bonus>0?`GiroFacile incentiva la mobilità elettrica: il tuo piano include fino a ${bonus} ${bonus===1?"veicolo elettrico aggiuntivo":"veicoli elettrici aggiuntivi"} senza consumare gli slot mezzi standard.`:"Il piano non prevede slot bonus elettrici aggiuntivi.";
    const warning=usage.over_limit?usage.message||"La flotta supera i limiti del piano attuale. I mezzi sono conservati: elimina i mezzi in eccesso, correggi l’alimentazione o scegli un piano adeguato.":usage.plan_active===false?"L’abbonamento non è attivo. I mezzi restano consultabili; rinnova il piano per aggiungerne altri.":"";
    return `<section class="gf-vehicle-usage" aria-label="Utilizzo slot mezzi">
      <div class="gf-vehicle-usage-grid">
        <div class="gf-vehicle-usage-card"><span>Mezzi inclusi nel piano</span><strong>${number(usage.standard_used)} <small>/ ${number(usage.standard_limit)} utilizzati</small></strong></div>
        <div class="gf-vehicle-usage-card electric"><span>Bonus mobilità elettrica <span aria-hidden="true">⚡</span></span><strong>${number(usage.bonus_used)} <small>/ ${number(usage.electric_bonus)} utilizzati</small></strong></div>
      </div>
      <p class="gf-vehicle-usage-note">${escape(benefit)}</p>
      <p class="gf-vehicle-usage-note">Gli elettrici utilizzano prima i bonus; quelli ulteriori occupano gli slot standard. Totale mezzi: ${number(usage.total_used)} / ${number(usage.total_limit)}.</p>
      ${warning?`<p class="gf-vehicle-usage-warning" role="status">${escape(warning)}</p>`:""}
    </section>`;
  }
  function formHint(usage,fuel,editingVehicle=null){
    if(!usage) return {tone:"neutral",text:"La disponibilità degli slot sarà verificata al salvataggio."};
    if(usage.plan_active===false) return {tone:"warning",text:"Abbonamento non attivo: rinnova il piano per aggiungere o modificare mezzi."};
    if(fuel==="elettrico"){
      if(Number(usage.bonus_remaining)>0 && (editingVehicle || usage.can_add_electric)) return {tone:"positive",text:"⚡ Questo veicolo rientra nel bonus mobilità elettrica del tuo piano."};
      if(!editingVehicle && !usage.can_add_electric) return {tone:"warning",text:usage.message||"Hai raggiunto il limite complessivo dei mezzi e dei bonus elettrici del piano."};
      return {tone:"neutral",text:"Gli elettrici utilizzano prima gli slot bonus disponibili e poi gli slot standard."};
    }
    if(!editingVehicle && !usage.can_add_non_electric){
      const remaining=Number(usage.bonus_remaining||0);
      return {tone:"warning",text:remaining>0?`Hai raggiunto il limite dei mezzi inclusi nel tuo piano. Hai ancora ${remaining} ${remaining===1?"slot bonus disponibile":"slot bonus disponibili"} per ${remaining===1?"un veicolo elettrico":"veicoli elettrici"}.`:usage.message||"Hai raggiunto il limite dei mezzi inclusi nel tuo piano."};
    }
    if(editingVehicle?.alimentazione==="elettrico") return {tone:"neutral",text:"Il cambio a un’alimentazione non elettrica è consentito solo se rispetta il limite degli slot standard; il controllo avviene al salvataggio."};
    return {tone:"neutral",text:"Solo l’alimentazione Elettrico può utilizzare gli slot bonus. I mezzi ibridi occupano slot standard."};
  }
  function renderHint(element,usage,fuel,editingVehicle){
    if(!element) return;
    const hint=formHint(usage,fuel,editingVehicle);
    element.textContent=hint.text;
    element.className=`gf-electric-form-hint ${hint.tone}`;
  }
  global.GiroFacileElectricVehicles={summaryHtml,formHint,renderHint,planBenefit};
})(window);
