// GiroFacile · widget per iPhone (app Scriptable).
// Il Super Admin sostituisce indirizzo e chiave quando premi «Copia script»: incollalo in Scriptable
// come nuovo script, poi aggiungi un widget Scriptable alla schermata Home e scegli questo script.
// La chiave legge solo i numeri riassuntivi; si revoca dal Super Admin (Server › Widget iPhone).
const GF_URL = "__GF_URL__";
const GF_KEY = "__GF_KEY__";

// Colori del tema GiroFacile (static/design-system/theme.css).
const C = {
  bg: new Color("#0f2250"), text: Color.white(), muted: new Color("#c9d4f0"), accent: new Color("#9cc0ff"),
  danger: new Color("#ff6b81"), warning: new Color("#f2b84b"), ok: new Color("#5fd3a2"),
};

async function load() {
  const req = new Request(GF_URL + "/api/widget/stats");
  req.headers = { Authorization: "Bearer " + GF_KEY };
  req.timeoutInterval = 15;
  const data = await req.loadJSON();
  if (req.response.statusCode !== 200) throw new Error(data.detail || "Errore " + req.response.statusCode);
  return data;
}

function tile(stack, value, label, color) {
  const box = stack.addStack();
  box.layoutVertically();
  const v = box.addText(String(value));
  v.font = Font.boldRoundedSystemFont(22); v.textColor = color || C.text; v.minimumScaleFactor = 0.6;
  const l = box.addText(label);
  l.font = Font.mediumSystemFont(10); l.textColor = C.muted; l.lineLimit = 1; l.minimumScaleFactor = 0.7;
}

function row(widget, items) {
  const line = widget.addStack();
  items.forEach(([value, label, color], i) => {
    if (i) line.addSpacer();
    tile(line, value, label, color);
  });
  widget.addSpacer(8);
}

const widget = new ListWidget();
widget.backgroundColor = C.bg;
widget.setPadding(14, 14, 12, 14);
widget.url = GF_URL + "/admin";
const title = widget.addText("GiroFacile");
title.font = Font.heavySystemFont(13); title.textColor = C.accent;
widget.addSpacer(8);

try {
  const d = await load();
  const family = config.widgetFamily || "large";
  const tickets = [d.ticket_aperti, "Ticket aperti", d.ticket_aperti ? C.warning : C.ok];
  const companies = [d.aziende_registrate, "Aziende"];
  if (family === "small") {
    row(widget, [tickets]);
    row(widget, [companies]);
  } else {
    row(widget, [tickets, [d.ticket_nuovi_oggi, "Ticket oggi"], companies]);
    row(widget, [[d.aziende_in_prova, "In prova"], [d.aziende_abbonate, "Abbonate", C.ok], [d.giri_in_corso, "Giri in corso"]]);
    if (family === "large" || family === "extraLarge") {
      row(widget, [[d.nuove_aziende_mese, "Nuove nel mese"], [d.giri_oggi, "Giri oggi"], [d.errori_24h, "Errori 24h", d.errori_24h ? C.danger : C.ok]]);
      row(widget, [["€ " + d.mrr_stimato, "MRR stimato", C.accent]]);
    }
  }
  widget.addSpacer();
  const time = new Date(d.aggiornato_alle).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  const foot = widget.addText("Aggiornato alle " + time);
  foot.font = Font.systemFont(9); foot.textColor = C.muted;
} catch (e) {
  const err = widget.addText("Dati non disponibili: " + e.message);
  err.font = Font.systemFont(11); err.textColor = C.danger;
}

// iOS decide quando aggiornare; chiediamo circa ogni 15 minuti.
widget.refreshAfterDate = new Date(Date.now() + 15 * 60 * 1000);
if (config.runsInWidget) Script.setWidget(widget);
else await widget.presentLarge();
Script.complete();
