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
// Destinazione per Google Maps: coordinate verificate della fermata («lat,lon»), altrimenti il testo dell'indirizzo.
function gfNavDestination(stop){
  const s = stop || {}, c = s.coord && typeof s.coord === "object" ? s.coord : s, lat = Number(c.lat), lon = Number(c.lon);
  const ok = c.lat != null && c.lon != null && c.lat !== "" && c.lon !== "" && Number.isFinite(lat) && Number.isFinite(lon)
    && Math.abs(lat) <= 90 && Math.abs(lon) <= 180 && !(lat === 0 && lon === 0);
  return ok ? `${lat.toFixed(6)},${lon.toFixed(6)}` : (s.indirizzo || "");
}
function gfDateIt(value){
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value||""));
  return m ? `${m[3]}/${m[2]}/${m[1]}` : (value || "");
}
