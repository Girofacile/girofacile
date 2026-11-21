import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Pill } from "../components/Pill";
import { Title } from "../components/Title";
import { Window } from "../components/Window";
import { ease, tween } from "../lib/theme";

// 5 · Orari di scarico, ZTL e sponda sulla schermata Clienti del gestionale.
export const Pilastro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <Title name="Titolo scarico ZTL sponda" lines={["Sa già orari di scarico,", "*ZTL *e *sponda."]} top={290} size={78} inAt={0.045} outAt={2.991} />
      <Window width={960} height={640} top={500} inAt={0.134} outAt={3.036}>
        <Img
          src={staticFile("ui/clienti.png")}
          style={{ display: "block", width: 960, translate: `0px ${tween(frame, fps, 0.357, 2.857, 0, -90, ease.power1InOut)}px` }}
        />
      </Window>
      <Pill top={830} kind="ok" inAt={0.893} outAt={2.991}>
        Fasce di scarico nel calcolo
      </Pill>
      <Pill top={940} kind="warn" inAt={1.205} outAt={3.027}>
        Avviso ZTL prima di partire
      </Pill>
      <Pill top={1050} kind="warn" inAt={1.518} outAt={3.063}>
        Avviso sponda per il mezzo
      </Pill>
    </AbsoluteFill>
  );
};
