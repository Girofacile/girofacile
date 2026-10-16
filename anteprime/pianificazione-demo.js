/* Layout prototypes only. No optimizer, API client, persistence or credentials. */
(function () {
  "use strict";
  const ROWS = [
  {
    "id": 1,
    "name": "Farmacia Centrale",
    "address": "Via Roma 12, Milano",
    "orders": 2,
    "colli": 8,
    "kg": 180,
    "window": "09:00–11:00",
    "unload": 10,
    "eta": "09:00",
    "leave": "09:10",
    "constraint": "ZTL"
  },
  {
    "id": 2,
    "name": "Alimentari Verdi",
    "address": "Via Volta 8, Sesto San Giovanni",
    "orders": 1,
    "colli": 5,
    "kg": 160,
    "window": "09:00–12:00",
    "unload": 15,
    "eta": "09:30",
    "leave": "09:45",
    "constraint": "Sponda"
  },
  {
    "id": 3,
    "name": "Hotel Aurora",
    "address": "Viale Monza 90, Milano",
    "orders": 1,
    "colli": 4,
    "kg": 120,
    "window": "10:00–12:00",
    "unload": 10,
    "eta": "10:00",
    "leave": "10:10",
    "constraint": "Attesa 5 min"
  },
  {
    "id": 4,
    "name": "Ristorante Portico",
    "address": "Via Dante 6, Bresso",
    "orders": 2,
    "colli": 7,
    "kg": 210,
    "window": "10:00–13:00",
    "unload": 15,
    "eta": "10:25",
    "leave": "10:40",
    "constraint": ""
  },
  {
    "id": 5,
    "name": "Market Nord",
    "address": "Via Libertà 20, Cinisello Balsamo",
    "orders": 1,
    "colli": 6,
    "kg": 240,
    "window": "09:00–12:00",
    "unload": 15,
    "eta": "11:00",
    "leave": "11:15",
    "constraint": "Sponda"
  },
  {
    "id": 6,
    "name": "Bar Giardino",
    "address": "Via Verdi 4, Milano",
    "orders": 1,
    "colli": 2,
    "kg": 70,
    "window": "09:00–12:00",
    "unload": 10,
    "eta": "11:30",
    "leave": "11:40",
    "constraint": ""
  }
];
  const $ = selector => document.querySelector(selector);
  const $$ = selector => Array.from(document.querySelectorAll(selector));
  const layout = document.body.dataset.previewLayout;
  const selected = new Set(ROWS.map(row => row.id));
  let calculated = false;
  let activeStage = "organize";
  let activeTab = "config";
  let dirty = false;
  const escape = value => String(value).replace(/[&<>"']/g, char =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  const chosen = () => ROWS.filter(row => selected.has(row.id));
  const value = id => document.getElementById(id).value;
  const field = (quantity, id) => $('[data-quantity="' + quantity + '"][data-stop-id="' + id + '"]');
  const money = amount => amount.toLocaleString("it-IT", {style: "currency", currency: "EUR"});
  const number = amount => amount.toLocaleString("it-IT", {maximumFractionDigits: 1});
  const label = id => document.getElementById(id).selectedOptions[0].textContent;
  const fleet = () => value("trip-mode") === "fleet";
  const resources = () => label("trip-vehicle").split(" · ")[0] + " · " + label("trip-driver") +
    (fleet() ? " + " + label("trip-vehicle-2").split(" · ")[0] + " · " + label("trip-driver-2") : "");
  function message(text, status) {
    const box = $("#preview-message");
    box.hidden = !text;
    box.textContent = text;
    box.dataset.status = status || "info";
  }
  function showStage(stage) {
    activeStage = stage;
    if (layout === "a") $$("[data-step-panel]").forEach(panel => {
      panel.hidden = panel.dataset.stepPanel !== stage || (stage === "review" && !calculated);
    });
    const order = ["selection", "organize", "review"];
    $$("[data-stage-label]").forEach(item => {
      item.classList.toggle("is-done", order.indexOf(item.dataset.stageLabel) < order.indexOf(stage));
      if (item.dataset.stageLabel === stage) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
    });
  }
  function showTab(target, focus) {
    if (target === "review" && !calculated) {
      message("Calcola prima il percorso per vedere il risultato.", "warning");
      return;
    }
    activeTab = target;
    $$('[role="tab"][data-target]').forEach(tab => {
      const current = tab.dataset.target === target;
      tab.setAttribute("aria-selected", String(current));
      tab.tabIndex = current ? 0 : -1;
      if (focus && current) tab.focus();
    });
    if (layout === "c") {
      $("#panel-config").hidden = target !== "config";
      $("#panel-stops").hidden = target !== "stops";
      $("#review-panel").hidden = target !== "review" || !calculated;
    }
  }
  function invalidate() {
    dirty = true;
    const wasCalculated = calculated;
    calculated = false;
    $("#review-panel").hidden = true;
    $("#success-panel").hidden = true;
    $$('[data-target="review"]').forEach(tab => tab.setAttribute("aria-disabled", "true"));
    if (layout === "c" && activeTab === "review") showTab("config");
    if (layout === "a" && activeStage === "review") showStage("organize");
    if (wasCalculated) message("Dati modificati. Ricalcola il percorso prima di programmare.", "warning");
    updateSummary();
  }
  function updateSummary() {
    const list = chosen();
    const customers = value("trip-source") === "customers";
    const orderCount = customers ? list.length : list.reduce((sum, row) => sum + row.orders, 0);
    const kg = list.reduce((sum, row) => sum + (Number(field("kg", row.id).value) || 0), 0);
    const colli = list.reduce((sum, row) => sum + (Number(field("colli", row.id).value) || 0), 0);
    const totals = {stops: list.length, orders: orderCount, kg: number(kg), colli: number(colli)};
    for (const [key, total] of Object.entries(totals)) $$('[data-total="' + key + '"]').forEach(node => {
      node.textContent = String(total);
    });
    $$("[data-source-label]").forEach(node => { node.textContent = customers ? "clienti" : "ordini"; });
    $$("[data-source-page]").forEach(node => { node.textContent = customers ? "Clienti" : "Ordini"; });
    $$("[data-source-order]").forEach(node => { node.hidden = customers; });
    $$("[data-source-customer]").forEach(node => { node.hidden = !customers; });
    $$("[data-delivery-row]").forEach(row => { row.hidden = !selected.has(Number(row.dataset.deliveryRow)); });
    $("#empty-selection").hidden = list.length > 0;
    $("#fleet-fields").hidden = !fleet();
    $("#trip-energy-price").disabled = value("trip-energy-mode") !== "custom";
    $("#trip-energy-price").previousElementSibling.textContent = value("trip-vehicle") === "ev01" ?
      "Prezzo energia (€/kWh)" : "Prezzo carburante (€/L)";
    $('[data-summary="departure"]').textContent =
      (value("trip-date") ? value("trip-date").split("-").reverse().join("/") : "Scegli la data") +
      " · " + (value("trip-time") || "Scegli l’orario");
    $('[data-summary="resources"]').textContent = resources();
    $('[data-summary="return"]').textContent = value("trip-return") === "yes" ?
      label("trip-depot").split(" · ")[0] : "Ultima consegna";
    $('[data-summary="estimate"]').textContent = calculated ?
      "58,0 km · 3 h 30 min · esempio" : "Disponibili dopo il calcolo";
    $$('[data-action="calculate"]').forEach(btn => { btn.disabled = list.length === 0; });
    ROWS.forEach(row => {
      $('[data-window-label="' + row.id + '"]').textContent = value("stop-window-" + row.id);
      $('[data-unload-label="' + row.id + '"]').textContent = value("stop-unload-" + row.id);
    });
    return {kg, colli, list};
  }
  function editSelection() {
    $("#success-panel").hidden = true;
    if (layout === "a") {
      showStage("selection");
      $('[data-step-panel="selection"]').scrollIntoView({block: "start"});
    } else {
      $("#selection-editor").open = true;
      $("#selection-editor").scrollIntoView({block: "start"});
    }
    $('[data-stop-choice="1"]').focus({preventScroll: true});
  }
  function continuePlanning() {
    if (!selected.size) { message("Seleziona almeno un ordine o un cliente.", "warning"); return; }
    if (layout === "a") showStage("organize");
    if ($("#selection-editor")) $("#selection-editor").open = false;
    if (layout === "c") showTab("config");
    message("");
    $("#config-title").scrollIntoView({block: "start"});
  }
  function editConfig() {
    $("#success-panel").hidden = true;
    if (layout === "a") showStage("organize");
    if (layout === "c") showTab("config");
    $("#trip-date").scrollIntoView({block: "center"});
    $("#trip-date").focus({preventScroll: true});
  }
  function timeAt(offset) {
    const parts = (value("trip-time") || "08:30").split(":").map(Number);
    const minutes = parts[0] * 60 + parts[1] + offset;
    return String(Math.floor(minutes / 60) % 24).padStart(2, "0") + ":" +
      String(minutes % 60).padStart(2, "0") + (minutes >= 1440 ? " (+1 giorno)" : "");
  }
  function renderResult() {
    const list = chosen();
    $('[data-review-resources]').textContent = resources();
    $('[data-review-time]').textContent = "Partenza " + value("trip-time") + " · " +
      (value("trip-return") === "yes" ? "rientro " : "ultima consegna ") +
      timeAt(value("trip-return") === "yes" ? 210 : 190) + " · esempio";
    $('[data-review-duration-unit]').textContent = fleet() ?
      "durata cumulata dei giri · esempio" : "guida, scarico e attese";
    const electric = value("trip-vehicle") === "ev01";
    const unitPrice = value("trip-energy-mode") === "custom" ? Number(value("trip-energy-price")) :
      (electric ? 0.30 : 1.75);
    const quantity = electric ? 45.8 : 5.8;
    const energyCost = quantity * unitPrice;
    $('[data-review-energy-label]').textContent = electric ? "Energia" : "Carburante";
    $('[data-review-energy]').textContent = number(quantity) + (electric ? " kWh · " : " L · ") + money(energyCost);
    $('[data-review-cost]').textContent = money(energyCost + 3.50);
    $("#demo-result-limit").hidden = !dirty && !fleet();
    const offsets = [30, 60, 90, 115, 150, 180];
    $("#review-stop-list").innerHTML = list.map((row, index) => {
      const group = fleet() && index % 3 === 0 ?
        '<li class="gf-stop"><span class="gf-stop__main"><strong>' +
        (index === 0 ? escape(label("trip-vehicle").split(" · ")[0]) : "Van 04") +
        " · " + (index === 0 ? escape(label("trip-driver")) : "Luca Conti") + "</strong></span></li>" : "";
      const eta = timeAt(offsets[fleet() ? index % 3 : index] || 30);
      return group + '<li class="gf-stop"><span class="gf-stop__number">' +
        (fleet() ? (index % 3) + 1 : index + 1) + '</span><span class="gf-stop__main">' +
        '<strong class="gf-stop__name">' + escape(row.name) + '</strong><span class="gf-stop__meta">' +
        escape(row.address) + '</span><span class="gf-stop__meta">Finestra ' +
        escape(value("stop-window-" + row.id)) + " · scarico " +
        escape(value("stop-unload-" + row.id)) + " min" +
        (row.id === 3 ? " · attesa di esempio 5 min" : "") +
        '</span></span><span class="gf-stop__time">' + eta + "</span></li>";
    }).join("");
    const points = [[160,130],[270,110],[335,185],[400,200],[520,90],[610,190]];
    const path = "M60 230 " + list.map(row => "L" + points[row.id - 1].join(" ")).join(" ") +
      (value("trip-return") === "yes" ? " L60 230" : "");
    $("#demo-map").innerHTML = '<svg viewBox="0 0 660 300" role="img" aria-label="Schema del percorso dimostrativo">' +
      '<g aria-hidden="true"><line class="gf-route-map__grid" x1="0" y1="75" x2="660" y2="75"/>' +
      '<line class="gf-route-map__grid" x1="0" y1="150" x2="660" y2="150"/>' +
      '<line class="gf-route-map__grid" x1="0" y1="225" x2="660" y2="225"/>' +
      '<line class="gf-route-map__grid" x1="165" y1="0" x2="165" y2="300"/>' +
      '<line class="gf-route-map__grid" x1="330" y1="0" x2="330" y2="300"/>' +
      '<line class="gf-route-map__grid" x1="495" y1="0" x2="495" y2="300"/></g>' +
      '<path class="gf-route-map__todo" d="' + path + '"/>' +
      '<g class="gf-route-map__depot"><rect x="34" y="216" width="52" height="28" rx="6"/>' +
      '<text x="60" y="230">DEP</text></g>' + list.map((row, index) =>
      '<g class="gf-route-map__node"><circle cx="' + points[row.id - 1][0] + '" cy="' +
      points[row.id - 1][1] + '" r="14"/><text x="' + points[row.id - 1][0] + '" y="' +
      points[row.id - 1][1] + '">' + (index + 1) + "</text></g>").join("") + "</svg>";
  }
  function calculate() {
    const totals = updateSummary();
    if (!totals.list.length) { message("Seleziona almeno una consegna.", "warning"); return; }
    for (const id of ["trip-date", "trip-time"]) {
      if (!document.getElementById(id).checkValidity()) {
        editConfig(); document.getElementById(id).reportValidity(); return;
      }
    }
    const invalidQuantity = totals.list.flatMap(row => [field("kg", row.id), field("colli", row.id)])
      .find(input => input.value === "" || !input.checkValidity());
    if (invalidQuantity) {
      if (layout === "a") showStage("organize");
      if (layout === "c") showTab("stops");
      message("Controlla colli e peso: usa valori validi, maggiori o uguali a zero.", "warning");
      invalidQuantity.focus(); return;
    }
    const capacity = (value("trip-vehicle") === "ev01" ? 1200 : 1500) + (fleet() ? 1500 : 0);
    if (totals.kg > capacity) { message("Il carico supera la capacità dei mezzi selezionati. Riduci le consegne o scegli la flotta.", "warning"); return; }
    calculated = true;
    $("#success-panel").hidden = true;
    renderResult();
    updateSummary();
    $("#review-panel").hidden = false;
    $$('[data-target="review"]').forEach(tab => tab.setAttribute("aria-disabled", "false"));
    if (layout === "a") showStage("review");
    if (layout === "c") showTab("review");
    message("");
    $("#review-panel").scrollIntoView({block: "start"});
    $("#review-panel").focus({preventScroll: true});
  }
  function program() {
    if (!calculated) { message("Ricalcola il percorso prima di programmare.", "warning"); return; }
    $("#success-panel").hidden = false;
    $('[data-success-summary]').textContent = chosen().length + " fermate · " + resources() + " · " +
      value("trip-date").split("-").reverse().join("/") + " alle " + value("trip-time");
    $("#success-panel").scrollIntoView({block: "start"});
    $("#success-panel").focus({preventScroll: true});
    message("Simulazione completata: nessuna richiesta API e nessun salvataggio.", "success");
  }
  function init() {
    document.addEventListener("click", event => {
      const tab = event.target.closest('[role="tab"][data-target]');
      if (tab) { showTab(tab.dataset.target, true); return; }
      const action = event.target.closest("[data-action]");
      if (action) {
        const actions = {"edit-selection": editSelection, "continue": continuePlanning,
          "calculate": calculate, "program": program, "edit-config": editConfig,
          "back-review": () => { $("#success-panel").hidden = true; $("#review-panel").scrollIntoView({block: "start"}); },
          "demo-secondary": () => message("Questa azione resta disponibile nel prodotto. L’anteprima mostra solo il layout e non esegue operazioni.")};
        if (actions[action.dataset.action]) actions[action.dataset.action]();
        return;
      }
      const shellLink = event.target.closest(".gf-sidebar a");
      if (shellLink) {
        event.preventDefault();
        if (["ordini", "clienti"].includes(shellLink.dataset.gfNav)) {
          $("#trip-source").value = shellLink.dataset.gfNav === "clienti" ? "customers" : "orders";
          invalidate(); updateSummary(); editSelection();
        } else message("Navigazione dimostrativa: nessuna pagina dell’azienda viene aperta.");
      }
    });
    document.addEventListener("keydown", event => {
      const tab = event.target.closest('[role="tab"][data-target]');
      if (!tab || !["ArrowRight","ArrowLeft","Home","End"].includes(event.key)) return;
      event.preventDefault();
      const tabs = $$('[role="tab"][data-target]').filter(node => node.getAttribute("aria-disabled") !== "true");
      const index = tabs.indexOf(tab);
      const target = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
        (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      showTab(tabs[target].dataset.target, true);
    });
    document.addEventListener("change", event => {
      const choice = event.target.closest("[data-stop-choice]");
      if (choice) {
        const id = Number(choice.dataset.stopChoice);
        if (choice.checked) selected.add(id); else selected.delete(id);
        invalidate(); updateSummary(); return;
      }
      if (event.target.matches("select")) { invalidate(); updateSummary(); }
    });
    document.addEventListener("input", event => {
      if (event.target.matches("input:not([type=checkbox])")) { invalidate(); updateSummary(); }
    });
    updateSummary();
    showStage("organize");
    if (layout === "c") showTab("config");
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
}());
