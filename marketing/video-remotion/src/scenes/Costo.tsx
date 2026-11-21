import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Pill, Strong } from "../components/Pill";
import { Title } from "../components/Title";
import { Window } from "../components/Window";
import { BLUE, ease, tween } from "../lib/theme";

// Riquadro "Carburante / energia" dentro la card dei KPI (usato anche dall'outro per la trasformazione).
export const RING = { x: 546, y: 606, w: 478, h: 158.4 };

// 7 · Il costo del gasolio, prima di partire: card Km totali / Carburante del gestionale.
export const Costo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ringIn = tween(frame, fps, 0.893, 0.446, 0, 1, ease.expoOut);
  const ringFill = tween(frame, fps, 3.214, 0.196, 5, 60, ease.power2In);
  return (
    <AbsoluteFill>
      <Title name="Titolo costo gasolio" lines={["Il costo del gasolio,", "*prima *di *partire."]} top={290} size={80} inAt={0.045} outAt={3.08} />
      <Window width={980} height={170} top={600} left={50} bar={false} inAt={0.134} outAt={3.304}>
        <Img src={staticFile("ui/kpi.png")} style={{ display: "block", width: 980 }} />
      </Window>
      <div
        style={{
          position: "absolute",
          left: RING.x,
          top: RING.y,
          width: RING.w,
          height: RING.h,
          border: `${ringFill}px solid ${BLUE}`,
          borderRadius: 26,
          zIndex: 6,
          opacity: frame >= 3.393 * fps ? 0 : ringIn,
          scale: `${1.08 - 0.08 * ringIn}`,
        }}
      />
      <Pill top={900} kind="ok" inAt={1.25} outAt={3.08}>
        <Strong>€ 14,51</Strong> di carburante stimato
      </Pill>
      <Pill top={1020} kind="ok" inAt={1.5625} outAt={3.125}>
        <Strong>67,7 km</Strong> per 12 consegne
      </Pill>
    </AbsoluteFill>
  );
};
