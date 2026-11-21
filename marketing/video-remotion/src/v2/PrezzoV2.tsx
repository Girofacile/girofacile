import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Pill, Strong } from "../components/Pill";
import { Title } from "../components/Title";
import { BLUE, DISPLAY, TEXT, ease, tween } from "../lib/theme";

// Prezzo medio nazionale gasolio self (Mimit): media nov 2025 = 1,683 €/l; 21/11/2026 = 2,198 €/l -> +31%.
const PRICE_THEN = 1.683;
const PRICE_NOW = 2.198;

// v2 · 2 Perché ora, sul blu. Una cosa alla volta: titolo, prezzo che sale, +31%.
export const PrezzoV2: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const numIn = tween(frame, fps, 0.5, 0.45, 0, 1, ease.expoOut);
  const price = tween(frame, fps, 0.9, 1.0, PRICE_THEN, PRICE_NOW, ease.power2InOut);
  const swapOut = tween(frame, fps, 1.7, 0.2, 0, 1, ease.power3In);
  const swapIn = tween(frame, fps, 1.9, 0.3, 0, 1, ease.expoOut);
  const fly = tween(frame, fps, 3.5, 0.45, 0, 1, ease.expoInOut);
  return (
    <AbsoluteFill style={{ translate: `0px ${-2000 * fly}px` }}>
      <AbsoluteFill style={{ backgroundColor: BLUE }} />
      <Title name="Titolo prezzo" lines={["Il gasolio costa", "un terzo in più."]} top={330} size={92} inAt={0.1} variant="light" />
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
        }}
      >
        {price.toFixed(2).replace(".", ",")} €
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, top: 900, height: 60, textAlign: "center", fontFamily: TEXT, fontSize: 44, fontWeight: 500, color: "rgba(255,255,255,.9)", opacity: numIn }}>
        <span style={{ position: "absolute", left: 0, right: 0, opacity: 1 - swapOut, translate: `0px ${-24 * swapOut}px` }}>al litro · un anno fa</span>
        <span style={{ position: "absolute", left: 0, right: 0, opacity: swapIn, translate: `0px ${24 * (1 - swapIn)}px` }}>al litro · oggi</span>
      </div>
      <Pill top={1010} kind="up" inAt={2.1}>
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
          opacity: tween(frame, fps, 2.3, 0.4, 0, 1, ease.power2InOut),
        }}
      >
        Prezzo medio gasolio self, Mimit · media nov 2025 → 21 nov 2026
      </div>
    </AbsoluteFill>
  );
};
