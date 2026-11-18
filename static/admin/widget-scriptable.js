// GiroFacile · widget per iPhone (app Scriptable).
// Il Super Admin sostituisce indirizzo e chiave quando premi «Copia script».
// Per aggiornare uno script già installato puoi mantenere le tue due righe qui sotto.
// La chiave legge solo i numeri riassuntivi e si revoca da Server › Widget iPhone.
const GF_URL = "__GF_URL__";
const GF_KEY = "__GF_KEY__";

// Colori adattivi di iOS, risolti dal sistema anche quando cambia il tema.
const adaptive = (light, dark) => Color.dynamic(new Color(light), new Color(dark));
const C = {
  bg: adaptive("f2f2f7", "1c1c1e"),
  surface: adaptive("ffffff", "2c2c2e"),
  blue: adaptive("007aff", "64a8ff"),
  ink: adaptive("1c1c1e", "f5f5f7"), muted: adaptive("636366", "aeaeb2"),
  soft: adaptive("e8f0ff", "23334d"),
  green: adaptive("248a3d", "32d74b"),
  danger: adaptive("c93436", "ff6961"), dangerSoft: adaptive("fff0ef", "462629"),
  warning: adaptive("946200", "ffd60a"),
};
const family = config.widgetFamily || "large";
const small = family === "small";
const medium = family === "medium";
const screen = Device.screenSize();
const shortSide = Math.min(screen.width, screen.height);
const compact = shortSide <= 375;
const padding = compact || medium ? 10 : 12;
// Margine prudente rispetto alla larghezza dei widget iPhone, anche con schermo ruotato.
const wideWidth = Math.min(380, shortSide - (shortSide > 400 ? 72 : shortSide >= 375 ? 60 : 48));
const smallWidth = shortSide < 350 ? 136 : compact ? 146 : 156;
const contentWidth = (small ? smallWidth : wideWidth) - padding * 2;
const gap = 6;

async function load() {
  const req = new Request(GF_URL + "/api/widget/stats");
  req.headers = { Authorization: "Bearer " + GF_KEY };
  req.timeoutInterval = 15;
  const data = await req.loadJSON();
  if (req.response.statusCode !== 200) {
    const error = new Error("Dati non disponibili");
    error.status = req.response.statusCode;
    throw error;
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("Dati non disponibili");
  return data;
}

function number(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}
function count(value) {
  const n = number(value);
  return n === null ? "—" : n.toLocaleString("it-IT", { maximumFractionDigits: 0 });
}
function euros(value) {
  const n = number(value);
  return n === null ? "—" : n.toLocaleString("it-IT", {
    style: "currency", currency: "EUR", minimumFractionDigits: Number.isInteger(n) ? 0 : 2,
    maximumFractionDigits: 2,
  });
}
function text(stack, value, size, color, weight = "medium") {
  const label = stack.addText(String(value));
  label.font = weight === "bold" ? Font.boldRoundedSystemFont(size) : Font.mediumSystemFont(size);
  label.textColor = color;
  label.lineLimit = 1;
  label.minimumScaleFactor = 0.65;
  return label;
}
function icon(stack, name, size, color) {
  const symbol = SFSymbol.named(name);
  if (!symbol) return;
  const image = stack.addImage(symbol.image);
  image.imageSize = new Size(size, size);
  image.tintColor = color;
}
function card(parent, width, height, background, inset = 8) {
  const box = parent.addStack();
  box.layoutVertically();
  box.size = new Size(width, height);
  box.backgroundColor = background;
  box.cornerRadius = 12;
  box.setPadding(inset, inset, inset, inset);
  return box;
}
function line(parent) {
  const stack = parent.addStack();
  stack.centerAlignContent();
  return stack;
}
function space(widget, flexible = false) {
  widget.addSpacer(compact ? 4 : 5);
  if (flexible) widget.addSpacer();
}
function header(widget) {
  const row = line(widget);
  icon(row, "location.fill", small || medium ? 11 : 13, C.blue);
  row.addSpacer(5);
  text(row, "GiroFacile", small || medium ? 12 : 14, C.ink, "bold");
  row.addSpacer();
}
function hero(parent, value, label, symbol, width, subtitle, primary) {
  const box = card(parent, width, compact ? 56 : 62, primary ? C.soft : C.surface, 4);
  const top = line(box);
  icon(top, symbol, 10, primary ? C.blue : C.muted);
  top.addSpacer(4);
  text(top, label, 10, primary ? C.blue : C.muted);
  text(box, count(value), compact ? 22 : 25, primary ? C.blue : C.ink, "bold");
  if (subtitle) text(box, subtitle, compact ? 8 : 9, C.muted);
}
function metricRow(widget, items, dense = false) {
  const row = widget.addStack();
  const width = (contentWidth - gap * (items.length - 1)) / items.length;
  items.forEach((item, index) => {
    if (index) row.addSpacer(gap);
    const primary = !!item.primary;
    const box = card(row, width, dense ? 43 : compact ? 36 : 42,
      primary ? C.soft : item.alert ? C.dangerSoft : C.surface,
      dense || compact ? 3 : 4);
    text(box, item.label, dense || compact ? 8 : 9, C.muted);
    box.addSpacer(1);
    text(box, count(item.value), dense || compact ? 17 : 20,
      primary ? C.blue : item.alert ? C.danger : item.green ? C.green : C.ink, "bold");
  });
}
function footer(widget, timestamp) {
  const date = typeof timestamp === "string" ? new Date(timestamp) : null;
  const valid = date && Number.isFinite(date.getTime());
  const old = valid && Date.now() - date.getTime() > 30 * 60 * 1000;
  let label = "Orario non disponibile";
  if (valid) {
    const time = date.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
    const today = date.toDateString() === new Date().toDateString();
    label = today ? (small ? "Agg. " : "Aggiornato alle ") + time
      : date.toLocaleDateString("it-IT", { day: "numeric", month: "short" }) + " · " + time;
    if (old) label = small ? "Dati " + (today ? time : label)
      : (today ? "Dati delle " + time : "Dati del " + label);
  }
  const row = line(widget);
  icon(row, old || !valid ? "clock" : "arrow.clockwise", 8, old ? C.warning : C.muted);
  row.addSpacer(4);
  text(row, label, small || medium ? 8 : 9, old ? C.warning : C.muted);
  row.addSpacer();
}
function renderSmall(widget, d) {
  widget.addSpacer(7);
  const box = card(widget, contentWidth, compact ? 48 : 52, C.soft, 6);
  text(box, "Ticket aperti", 10, C.muted);
  text(box, count(d.ticket_aperti), 26, C.blue, "bold");
  widget.addSpacer();
  const companies = line(widget);
  text(companies, "Aziende", 11, C.muted);
  companies.addSpacer();
  text(companies, count(d.aziende_registrate), 24, C.ink, "bold");
  widget.addSpacer(5);
}
function renderMedium(widget, d) {
  space(widget);
  metricRow(widget, [
    { value: d.ticket_aperti, label: "Ticket aperti", primary: true },
    { value: d.ticket_nuovi_oggi, label: "Ticket oggi" },
    { value: d.aziende_registrate, label: "Aziende" },
  ], true);
  space(widget);
  metricRow(widget, [
    { value: d.aziende_in_prova, label: "In prova" },
    { value: d.aziende_abbonate, label: "Abbonate", green: true },
    { value: d.giri_in_corso, label: "Giri in corso" },
  ], true);
  widget.addSpacer();
  widget.addSpacer(4);
}
function renderLarge(widget, d) {
  space(widget, true);
  const heroes = widget.addStack();
  const width = (contentWidth - gap) / 2;
  hero(heroes, d.ticket_aperti, "Ticket aperti", "tray", width,
    "Ticket oggi · " + count(d.ticket_nuovi_oggi), true);
  heroes.addSpacer(gap);
  hero(heroes, d.aziende_registrate, "Aziende", "building.2", width, "Registrate", false);
  space(widget, true);
  metricRow(widget, [
    { value: d.aziende_in_prova, label: "In prova" },
    { value: d.aziende_abbonate, label: "Abbonate", green: true },
    { value: d.nuove_aziende_mese, label: "Nuove nel mese" },
  ]);
  widget.addSpacer(gap);
  metricRow(widget, [
    { value: d.giri_oggi, label: "Giri oggi" },
    { value: d.giri_in_corso, label: "In corso" },
    { value: d.errori_24h, label: "Errori 24h", alert: number(d.errori_24h) > 0 },
  ]);
  space(widget, true);
  const revenue = widget.addStack();
  revenue.size = new Size(contentWidth, compact ? 26 : 30);
  revenue.backgroundColor = C.surface;
  revenue.cornerRadius = 12;
  revenue.setPadding(4, 8, 4, 8);
  revenue.centerAlignContent();
  text(revenue, "MRR stimato", 10, C.muted);
  revenue.addSpacer();
  text(revenue, euros(d.mrr_stimato), compact ? 18 : 20, C.ink, "bold");
  space(widget, true);
}
function renderError(widget, error) {
  widget.addSpacer();
  const box = widget.addStack();
  box.layoutVertically();
  icon(box, "wifi.exclamationmark", 23, C.blue);
  box.addSpacer(8);
  const auth = error.status === 401 || error.status === 403;
  text(box, auth ? "Collegamento da aggiornare" : "Dati non disponibili", small ? 12 : 15, C.ink, "bold");
  box.addSpacer(5);
  const detail = text(box, auth ? "Copia di nuovo lo script dal pannello Admin." : "Riprova con una connessione attiva.", 11, C.muted);
  detail.lineLimit = 2;
  widget.addSpacer();
}

const widget = new ListWidget();
widget.backgroundColor = C.bg;
widget.setPadding(padding, padding, padding, padding);
widget.url = GF_URL + "/admin";
header(widget);
try {
  const d = await load();
  if (small) renderSmall(widget, d);
  else if (medium) renderMedium(widget, d);
  else renderLarge(widget, d);
  footer(widget, d.aggiornato_alle);
} catch (error) {
  renderError(widget, error);
}

// La frequenza effettiva è decisa da iOS, anche quando il widget è aggiornato.
widget.refreshAfterDate = new Date(Date.now() + 15 * 60 * 1000);
if (config.runsInWidget) Script.setWidget(widget);
else if (small) await widget.presentSmall();
else if (medium) await widget.presentMedium();
else await widget.presentLarge();
Script.complete();
