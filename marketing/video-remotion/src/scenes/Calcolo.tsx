import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Pill, Strong } from "../components/Pill";
import { Title } from "../components/Title";
import { Window } from "../components/Window";
import { ease, tween } from "../lib/theme";

// 6 · Un clic, giri pronti: schermata "Controlla la suddivisione" del gestionale.
export const Calcolo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <Title name="Titolo un clic" lines={["Un clic.", "*Giri *pronti."]} top={290} inAt={0.045} outAt={2.902} />
      <Window width={980} height={573} top={560} inAt={0.134} outAt={2.946}>
        <Img
          src={staticFile("ui/suddivisione.png")}
          style={{ display: "block", width: 980, transformOrigin: "50% 0%", scale: `${tween(frame, fps, 0.446, 2.857, 1, 1.12, ease.power1InOut)}` }}
        />
      </Window>
      <Pill top={1110} kind="ok" inAt={0.893} outAt={2.946}>
        <Strong>3 giri</Strong> calcolati in automatico
      </Pill>
    </AbsoluteFill>
  );
};
