import React from "react";
import { Img, interpolateColors, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import route from "../data/route.json";
import { BLUE, INK, MUTED, NAVY, TEXT, ease, tween } from "../lib/theme";

type Pt = [number, number];
const MESS = route.mess as Pt[];
const OPT = route.opt as Pt[];

/** Etichetta con l'orologio: "Lunedì · 6:30". Dice al pubblico in che momento della giornata siamo. */
export const DayChip: React.FC<{ inAt: number; outAt?: number; children: React.ReactNode; light?: boolean }> = ({ inAt, outAt, children, light }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = tween(frame, fps, inAt, 0.45, 0, 1, ease.spring);
  const q = outAt === undefined ? 0 : tween(frame, fps, outAt, 0.25, 0, 1, ease.power3In);
  return (
    <div
      style={{
        position: "absolute",
        left: "50%",
        top: 290,
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "12px 30px 12px 16px",
        borderRadius: 999,
        background: light ? "rgba(255,255,255,.16)" : "#eef3ff",
        color: light ? "#ffffff" : NAVY,
        fontFamily: TEXT,
        fontWeight: 600,
        fontSize: 40,
        whiteSpace: "nowrap",
        opacity: p * (1 - q),
        translate: `-50% ${-20 * (1 - p) - 16 * q}px`,
      }}
    >
      <svg width={44} height={44} viewBox="0 0 24 24">
        <circle cx={12} cy={12} r={10} fill={light ? "#ffffff" : BLUE} />
        <path d="M12 6.5V12l3.5 2.2" stroke={light ? BLUE : "#ffffff"} strokeWidth={2.2} strokeLinecap="round" fill="none" />
      </svg>
      {children}
    </div>
  );
};

/** Punto lungo il percorso ricampionato (i punti sono equidistanti, quindi l'indice è proporzionale alla distanza). */
const at = (pts: Pt[], u: number): Pt => {
  const f = Math.max(0, Math.min(1, u)) * (pts.length - 1);
  const i = Math.min(pts.length - 2, Math.floor(f));
  const t = f - i;
  return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t];
};

/** Mappa stradale vera di Bologna con il furgone che percorre il giro e lascia la scia. */
export const VanMap: React.FC<{ which: "mess" | "opt"; progress: number; stopsIn: number; offsetY?: number }> = ({ which, progress, stopsIn, offsetY = -30 }) => {
  const pts = which === "mess" ? MESS : OPT;
  const col = which === "mess" ? "#4b5570" : BLUE;
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0]} ${p[1]}`).join(" ");
  const van = at(pts, progress);
  const W = route.mapW;
  const H = route.mapH;
  // fermata "servita" quando il furgone ci passa vicino
  const visited = (s: Pt) => {
    const n = Math.floor(progress * (pts.length - 1));
    for (let k = 0; k <= n; k += 2) if (Math.hypot(pts[k][0] - s[0], pts[k][1] - s[1]) < 16) return true;
    return false;
  };
  return (
    <div style={{ position: "absolute", left: 0, top: offsetY, width: W, height: H }}>
      <Img src={staticFile("map/bologna.jpg")} style={{ position: "absolute", width: W, height: H, filter: "saturate(.75)" }} />
      <div style={{ position: "absolute", inset: 0, background: "rgba(255,255,255,.42)" }} />
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ position: "absolute", inset: 0 }}>
        <path d={d} fill="none" stroke="#ffffff" strokeWidth={14} strokeLinejoin="round" strokeLinecap="round" pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - progress} opacity={progress > 0 ? 0.95 : 0} />
        <path d={d} fill="none" stroke={col} strokeWidth={8} strokeLinejoin="round" strokeLinecap="round" pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - progress} opacity={progress > 0 ? 1 : 0} />
        {(route.stops as Pt[]).map((s, i) => (
          <circle
            key={i}
            cx={s[0]}
            cy={s[1]}
            r={14}
            fill={visited(s) ? (which === "mess" ? "#4b5570" : BLUE) : "#ffffff"}
            stroke={which === "mess" ? NAVY : BLUE}
            strokeWidth={6}
            style={{ transformBox: "fill-box", transformOrigin: "50% 50%", scale: `${Math.max(0, Math.min(1, stopsIn * 13 - i))}` }}
          />
        ))}
        <rect x={route.depot[0] - 24} y={route.depot[1] - 24} width={48} height={48} rx={12} fill={NAVY} />
        {/* furgone */}
        <g transform={`translate(${van[0]} ${van[1]})`} opacity={stopsIn >= 1 ? 1 : 0}>
          <circle r={34} fill={which === "mess" ? NAVY : BLUE} stroke="#ffffff" strokeWidth={5} />
          <g transform="translate(-19 -13)" fill="#ffffff">
            <rect x={0} y={2} width={24} height={16} rx={2.5} />
            <path d="M25 7h6.5l5.5 6v5H25z" />
            <circle cx={8} cy={21} r={4.2} stroke={which === "mess" ? NAVY : BLUE} strokeWidth={2} />
            <circle cx={30} cy={21} r={4.2} stroke={which === "mess" ? NAVY : BLUE} strokeWidth={2} />
          </g>
        </g>
      </svg>
      <div style={{ position: "absolute", right: 0, top: -offsetY, padding: "4px 14px", background: "rgba(255,255,255,.85)", borderBottomLeftRadius: 12, fontFamily: TEXT, fontSize: 28, fontWeight: 500, color: MUTED }}>
        © OpenStreetMap
      </div>
    </div>
  );
};

/** Riga grande con icona: una cosa che GiroFacile sa già. */
export const FactRow: React.FC<{ top: number; inAt: number; outAt: number; kind: "ok" | "warn"; title: string; sub: string }> = ({ top, inAt, outAt, kind, title, sub }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = tween(frame, fps, inAt, 0.5, 0, 1, ease.spring);
  const q = tween(frame, fps, outAt, 0.25, 0, 1, ease.power3In);
  return (
    <div
      style={{
        position: "absolute",
        left: 120,
        right: 120,
        top,
        display: "flex",
        alignItems: "center",
        gap: 30,
        padding: "26px 34px",
        borderRadius: 32,
        background: "#ffffff",
        boxShadow: "0 16px 44px rgba(15,34,80,.12), 0 0 0 1.5px #e6eaf2",
        opacity: Math.min(1, p * 1.6) * (1 - q),
        translate: `${60 * (1 - p)}px ${-20 * q}px`,
      }}
    >
      <b
        style={{
          flex: "0 0 auto",
          width: 76,
          height: 76,
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: TEXT,
          fontSize: 44,
          fontWeight: 600,
          background: kind === "ok" ? "#e4edff" : "#fff1d6",
          color: kind === "ok" ? BLUE : "#b25e00",
        }}
      >
        {kind === "ok" ? "✓" : "!"}
      </b>
      <div style={{ fontFamily: TEXT }}>
        <div style={{ fontSize: 52, fontWeight: 600, color: INK, lineHeight: 1.1 }}>{title}</div>
        <div style={{ fontSize: 34, fontWeight: 500, color: MUTED, marginTop: 4 }}>{sub}</div>
      </div>
    </div>
  );
};

export const mix = (c: number) => interpolateColors(c, [0, 1], [NAVY, BLUE]);
