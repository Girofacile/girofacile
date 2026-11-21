import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Pill, Strong } from "../components/Pill";
import { Title } from "../components/Title";
import { BLUE, DISPLAY, TEXT, ease, tween } from "../lib/theme";

// Prezzo medio nazionale gasolio self (Mimit):
// media novembre 2025 = 1,683 €/l (open data Mimit, scheda mensile Figisc)
// 21 novembre 2026 = 2,198 €/l (Osservatorio prezzi Mimit, ANSA 21/11/2026)  ->  +30,6% = +31%
const PRICE_THEN = 1.683;
const PRICE_NOW = 2.198;

// 2 · Perché ora, sul blu: il prezzo del gasolio sale. Poi il blu vola via verso l'alto.
export const Stat: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const price = tween(frame, fps, 0.67, 0.759, PRICE_THEN, PRICE_NOW, ease.power2InOut);
  const numIn = tween(frame, fps, 0.402, 0.446, 0, 1, ease.expoOut);
  const pulse = tween(frame, fps, 1.429, 0.107, 0, 1, ease.power2Out) - tween(frame, fps, 1.536, 0.107, 0, 1, ease.power2Out);
  const labA = tween(frame, fps, 0.536, 0.268, 0, 1, ease.power2InOut) - tween(frame, fps, 1.384, 0.18, 0, 1, ease.power2InOut);
  const labB = tween(frame, fps, 1.429, 0.268, 0, 1, ease.expoOut);
  const out = tween(frame, fps, 2.8125, 0.268, 0, 1, ease.power3In);
  const fly = tween(frame, fps, 2.857, 0.402, 0, 1, ease.expoInOut);

  return (
    <AbsoluteFill style={{ translate: `0px ${-2000 * fly}px` }}>
      <AbsoluteFill style={{ backgroundColor: BLUE }} />
      <AbsoluteFill style={{ opacity: 1 - out, filter: `blur(${12 * out}px)`, translate: `0px ${-80 * out}px` }}>
        <Title name="Titolo prezzo" lines={["Il gasolio costa", "un terzo in più."]} top={330} size={92} inAt={0.045} variant="light" />
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: 620,
            textAlign: "center",
            fontFamily: DISPLAY,
            fontWeight: 700,
            fontSize: 250,
            letterSpacing: "-0.04em",
            lineHeight: 1,
            color: "#ffffff",
            opacity: numIn,
            translate: `0px ${60 * (1 - numIn)}px`,
            filter: `blur(${12 * (1 - numIn)}px)`,
            scale: `${1 + 0.06 * pulse}`,
          }}
        >
          {price.toFixed(2).replace(".", ",")} €
        </div>
        <div style={{ position: "absolute", left: 0, right: 0, top: 900, height: 60, textAlign: "center", fontFamily: TEXT, fontSize: 44, fontWeight: 500, color: "rgba(255,255,255,.88)" }}>
          <span style={{ position: "absolute", left: 0, right: 0, opacity: labA, translate: `0px ${frame > 1.384 * fps ? -20 * (1 - labA) : 0}px` }}>al litro · un anno fa</span>
          <span style={{ position: "absolute", left: 0, right: 0, opacity: labB, translate: `0px ${20 * (1 - labB)}px` }}>al litro · oggi</span>
        </div>
        <Pill top={1010} kind="up" inAt={1.518}>
          <Strong>+31%</Strong> in un anno
        </Pill>
        <div
          style={{
            position: "absolute",
            left: 60,
            right: 60,
            top: 1130,
            textAlign: "center",
            fontFamily: TEXT,
            fontSize: 28,
            fontWeight: 500,
            color: "rgba(255,255,255,.8)",
            opacity: tween(frame, fps, 1.563, 0.357, 0, 1, ease.power2InOut),
          }}
        >
          Prezzo medio gasolio self, Mimit · media nov 2025 → 21 nov 2026
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
