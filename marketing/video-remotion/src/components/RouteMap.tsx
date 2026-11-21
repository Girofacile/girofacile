import React from "react";
import { Img, interpolateColors, staticFile } from "remotion";
import route from "../data/route.json";
import { BLUE, NAVY } from "../lib/theme";

// Mappa stradale vera (tessere OpenStreetMap, come nel gestionale) di Bologna con le 12 fermate demo.
// "mess" = giro in ordine sbagliato, "opt" = giro più corto; entrambi su strade vere (OSRM),
// ricampionati con lo stesso numero di punti così il giro può "riordinarsi".
type Pt = [number, number];
const MESS = route.mess as Pt[];
const OPT = route.opt as Pt[];

export const RouteMap: React.FC<{
  /** 0 = giro a occhio, 1 = giro più corto */
  morph: number;
  /** 0 = grigio, 1 = blu */
  color: number;
  /** quanto del percorso è disegnato (0..1) */
  draw: number;
  /** scala di ogni fermata (per farle comparire una alla volta) */
  stopScale: (i: number) => number;
}> = ({ morph, color, draw, stopScale }) => {
  const d = MESS.map((p, i) => {
    const x = p[0] + (OPT[i][0] - p[0]) * morph;
    const y = p[1] + (OPT[i][1] - p[1]) * morph;
    return `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  const stroke = interpolateColors(color, [0, 1], ["#4b5570", BLUE]);
  const W = route.mapW;
  const H = route.mapH;
  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H }}>
      <Img src={staticFile("map/bologna.jpg")} style={{ position: "absolute", width: W, height: H, filter: "saturate(.75)" }} />
      <div style={{ position: "absolute", inset: 0, background: "rgba(255,255,255,.38)" }} />
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ position: "absolute", inset: 0 }}>
        <path d={d} fill="none" stroke="#ffffff" strokeWidth={13} strokeLinejoin="round" strokeLinecap="round" pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - draw} opacity={draw > 0 ? 0.95 : 0} />
        <path d={d} fill="none" stroke={stroke} strokeWidth={7} strokeLinejoin="round" strokeLinecap="round" pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - draw} opacity={draw > 0 ? 1 : 0} />
        {route.stops.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={14} fill="#ffffff" stroke={interpolateColors(color, [0, 1], [NAVY, BLUE])} strokeWidth={6} style={{ transformBox: "fill-box", transformOrigin: "50% 50%", scale: `${stopScale(i)}` }} />
        ))}
        <rect x={route.depot[0] - 24} y={route.depot[1] - 24} width={48} height={48} rx={12} fill={NAVY} />
      </svg>
      {/* attribuzione obbligatoria delle tessere OSM */}
      <div style={{ position: "absolute", right: 0, top: 0, padding: "4px 14px", background: "rgba(255,255,255,.85)", borderBottomLeftRadius: 12, fontFamily: "IBM Plex Sans", fontSize: 28, fontWeight: 500, color: "#5a6680" }}>
        © OpenStreetMap
      </div>
    </div>
  );
};
