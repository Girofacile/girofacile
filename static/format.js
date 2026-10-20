// Numeri e date nel formato italiano usato in tutto il gestionale.
function gfDecimal(v, digits=2){
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString("it-IT", {maximumFractionDigits:digits}) : "-";
}
// "1 fermata", "3 fermate".
function gfCount(n, one, many){ const v = Number(n)||0; return `${v} ${v===1?one:many}`; }
// Motivo di mancata consegna registrato dall'autista: stesse etichette del portale autista.
const GF_MISSED_REASONS = {assente:'Cliente assente', chiuso:'Attività chiusa', rifiutato:'Consegna rifiutata', altro:'Altro motivo'};
function gfMissedReason(code){ return code ? (GF_MISSED_REASONS[code] || code) : ''; }
function gfKm(v){ return (v === null || v === undefined || v === "") ? "- km" : `${gfDecimal(v)} km`; }
function gfDateIt(value){
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value||""));
  return m ? `${m[3]}/${m[2]}/${m[1]}` : (value || "");
}
