(function(global){
  "use strict";
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const money = value => value === null || value === undefined ? "Non disponibile" : "€ " + Number(value).toLocaleString("it-IT", {minimumFractionDigits:2,maximumFractionDigits:2});
  function summaryHtml(route, refreshAction=""){
    const toll = route.toll_estimated_eur;
    const pending = route.traffic_status === "not_requested";
    const note = route.toll_status === "partial" ? "Copertura parziale dei tratti a pedaggio" :
                 toll == null ? (pending ? "Disponibile alla programmazione, se i dati stradali lo consentono" : "Dati sui pedaggi non disponibili") : "";
    const updated = route.traffic_calculated_at ? new Date(route.traffic_calculated_at).toLocaleString("it-IT") : "";
    const canRefresh = refreshAction && route.id && ["bozza","programmato"].includes(route.status);
    const energyUnit = route.energy_unit || "L";
    return '<section class="gf-routing-summary" aria-label="Traffico e costi del giro">' +
      '<div class="gf-routing-eta"><strong>' + escape(route.eta_label || "ETA storico salvato") + '</strong>' +
      (route.traffic_status === "updated" && updated ? '<small>Traffico calcolato: ' + escape(updated) + '</small>' : '') +
      (route.traffic_status === "unavailable" ? '<small>Traffico non disponibile; utilizzati i tempi stradali salvati.</small>' : '') +
      (canRefresh ? '<button type="button" class="btn-secondary" onclick="' + escape(refreshAction) + '">Aggiorna ETA con traffico</button>' : '') + '</div>' +
      '<div class="gf-routing-costs"><div><span>Carburante / energia stimata</span><strong>' + money(route.costo_carburante) + '</strong>' +
      (route.energy_quantity_primary != null ? '<small>' + (energyUnit === "kWh" ? escape(route.energy_quantity_electric) + " kWh" : escape(route.energy_quantity_primary) + " " + escape(energyUnit) +
      (Number(route.energy_quantity_electric) > 0 ? " + " + escape(route.energy_quantity_electric) + " kWh" : "")) + '</small>' : '') + '</div>' +
      '<div><span>Pedaggio stimato</span><strong>' + money(toll) + '</strong>' + (note ? '<small>' + escape(note) + '</small>' : '') + '</div>' +
      '<div><span>Costo operativo stimato</span><strong>' + money(route.costo_totale ?? route.costo_carburante) + '</strong>' +
      (route.operating_cost_status === "partial" ? '<small>Totale parziale: pedaggi incompleti</small>' : '') + '</div></div></section>';
  }
  global.GiroFacileRouting = {summaryHtml};
})(window);
