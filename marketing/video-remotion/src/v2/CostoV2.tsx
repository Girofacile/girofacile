import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Pill, Strong } from "../components/Pill";
import { Title } from "../components/Title";
import { Window } from "../components/Window";
import { BLUE, ease, tween } from "../lib/theme";

// Riquadro blu attorno alla card "Carburante / energia" (l'outro parte da qui).
export const RING = { x: 172, y: 612, w: 736, h: 240.5 };

// v2 · 6 Il costo del gasolio, prima di partire: la sola card Carburante del gestionale, ingrandita.
export const CostoV2: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ringIn = tween(frame, fps, 0.9, 0.45, 0, 1, ease.expoOut);
  const ringFill = tween(frame, fps, 3.0, 0.22, 6, 120, ease.power2In);
  return (
    <AbsoluteFill>
      <Title name="Titolo costo gasolio" lines={["Il costo del gasolio,", "*prima *di *partire."]} top={330} size={80} inAt={0.05} outAt={2.8} />
      <Window width={720} height={224.5} top={620} left={180} bar={false} inAt={0.2} outAt={3.0}>
        <Img src={staticFile("ui/carburante.png")} style={{ display: "block", width: 720 }} />
      </Window>
      <div
        style={{
          position: "absolute",
          left: RING.x,
          top: RING.y,
          width: RING.w,
          height: RING.h,
          border: `${ringFill}px solid ${BLUE}`,
          borderRadius: 30,
          zIndex: 6,
          opacity: frame >= 3.3 * fps ? 0 : ringIn,
          scale: `${1.08 - 0.08 * ringIn}`,
        }}
      />
      <Pill top={940} kind="ok" inAt={1.4} outAt={2.8}>
        <Strong>3 giri</Strong> · 12 consegne · 67,7 km
      </Pill>
    </AbsoluteFill>
  );
};
