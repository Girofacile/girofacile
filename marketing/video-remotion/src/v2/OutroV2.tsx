import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Title } from "../components/Title";
import { BLUE, DISPLAY, MUTED, NAVY, TEXT, ease, tween } from "../lib/theme";
import { RING } from "./CostoV2";

const TILE = { x: 450, y: 480, s: 180 };

// v2 · 7 Outro (stessa logica della v1, tempi più distesi): il riquadro blu del carburante si riempie, ruota e diventa l'icona di GiroFacile.
export const OutroV2: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const m = tween(frame, fps, 0, 0.6, 0, 1, ease.expoInOut);
  const dx = RING.x + RING.w / 2 - (TILE.x + TILE.s / 2);
  const dy = RING.y + RING.h / 2 - (TILE.y + TILE.s / 2);
  const tileOn = frame >= 0.62 * fps;
  const icon = tween(frame, fps, 0.62, 0.5, 0, 1, ease.expoOut);
  const pop = tween(frame, fps, 0.62, 0.107, 0, 1, ease.power2Out) - tween(frame, fps, 0.727, 0.107, 0, 1, ease.power2Out);
  const arc = tween(frame, fps, 0.75, 0.75, 0, 1, ease.power3Out);
  const dots = tween(frame, fps, 1.15, 0.55, 0, 1, ease.expoOut);
  const ctaBg = tween(frame, fps, 2.0, 0.45, 0, 1, ease.expoInOut);
  const ctaTx = tween(frame, fps, 2.3, 0.4, 0, 1, ease.expoOut);
  // pulsazione del tasto: due battiti morbidi
  const beat = (t: number) => tween(frame, fps, t, 0.223, 0, 1, ease.sineInOut) - tween(frame, fps, t + 0.223, 0.223, 0, 1, ease.sineInOut);
  const pulse = beat(3.2) + beat(3.75) + beat(4.2);
  const url = tween(frame, fps, 2.6, 0.55, 0, 1, ease.power2InOut);

  return (
    <AbsoluteFill>
      {/* riquadro blu che vola dal KPI carburante alla posizione dell'icona */}
      <div
        style={{
          position: "absolute",
          left: TILE.x,
          top: TILE.y,
          width: TILE.s,
          height: TILE.s,
          borderRadius: "24%",
          background: BLUE,
          zIndex: 7,
          opacity: tileOn ? 0 : 1,
          translate: `${dx * (1 - m)}px ${dy * (1 - m)}px`,
          scale: `${RING.w / TILE.s + (1 - RING.w / TILE.s) * m} ${RING.h / TILE.s + (1 - RING.h / TILE.s) * m}`,
          rotate: `${360 * m}deg`,
        }}
      />
      {/* logo con anello */}
      <div style={{ position: "absolute", left: 540 - 150, top: TILE.y + TILE.s / 2 - 150, width: 300, height: 300, zIndex: 8 }}>
        <svg width={300} height={300} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
          <circle
            cx={150}
            cy={150}
            r={140}
            fill="none"
            stroke={BLUE}
            strokeWidth={7}
            strokeLinecap="round"
            pathLength={1}
            strokeDasharray="0.62 1"
            strokeDashoffset={0.62 * (1 - arc)}
            opacity={arc}
            transform="rotate(130 150 150)"
          />
          <circle
            cx={150}
            cy={150}
            r={140}
            fill="none"
            stroke={BLUE}
            strokeWidth={5}
            strokeLinecap="round"
            pathLength={1}
            strokeDasharray="0.001 0.03"
            opacity={dots}
            transform={`rotate(${-160 + 60 * dots} 150 150)`}
          />
        </svg>
        <div
          style={{
            position: "absolute",
            left: 60,
            top: 60,
            width: 180,
            height: 180,
            borderRadius: "24%",
            overflow: "hidden",
            opacity: tileOn ? 1 : 0,
            scale: `${1 + 0.12 * pop}`,
          }}
        >
          <Img src={staticFile("logo.png")} style={{ width: "100%", height: "100%", scale: `${0.55 + 0.45 * icon}`, rotate: `${-90 + 90 * icon}deg` }} />
        </div>
      </div>
      {/* nome: lettere che salgono una per una */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: TILE.y + TILE.s / 2 + 150,
          textAlign: "center",
          fontFamily: DISPLAY,
          fontWeight: 700,
          fontSize: 124,
          letterSpacing: "-0.03em",
          color: NAVY,
          perspective: 600,
        }}
      >
        {"GiroFacile".split("").map((ch, i) => {
          const p = tween(frame, fps, 0.85 + i * 0.035, 0.5, 0, 1, ease.expoOut);
          return (
            <span
              key={i}
              style={{
                display: "inline-block",
                opacity: p,
                translate: `0px ${70 * (1 - p)}px`,
                transform: `rotateX(${-80 * (1 - p)}deg)`,
                filter: `blur(${8 * (1 - p)}px)`,
              }}
            >
              {ch}
            </span>
          );
        })}
      </div>
      <Title name="Payoff" lines={["I giri di domani,", "*pronti *in *pochi *minuti."]} top={TILE.y + TILE.s / 2 + 290} size={54} inAt={1.45} variant="sub" />
      {/* tasto che si apre dal centro e pulsa */}
      <div
        style={{
          position: "absolute",
          left: 250,
          top: TILE.y + TILE.s / 2 + 440,
          width: 580,
          height: 96,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: TEXT,
          fontSize: 40,
          fontWeight: 600,
          color: "#ffffff",
          scale: `${1 + 0.04 * pulse}`,
        }}
      >
        <div style={{ position: "absolute", inset: 0, borderRadius: 999, background: BLUE, boxShadow: "0 12px 28px rgba(22,101,255,.28)", scale: `${ctaBg} 1`, opacity: ctaBg > 0 ? 1 : 0 }} />
        <span style={{ position: "relative", opacity: ctaTx, translate: `0px ${30 * (1 - ctaTx)}px` }}>Provalo gratis sui tuoi giri</span>
      </div>
      {/* scritta che si scrive da sinistra */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: TILE.y + TILE.s / 2 + 565,
          textAlign: "center",
          fontFamily: TEXT,
          fontSize: 40,
          fontWeight: 500,
          color: MUTED,
        }}
      >
        <span style={{ display: "inline-block", opacity: url > 0 ? 1 : 0, clipPath: `inset(0 ${100 - 100 * url}% 0 0)` }}>14 giorni gratis · girofacile.it</span>
      </div>
    </AbsoluteFill>
  );
};
