import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Pill } from "../components/Pill";
import { RouteMap } from "../components/RouteMap";
import { Title } from "../components/Title";
import { Window } from "../components/Window";
import { ease, tween } from "../lib/theme";

// 4 · Soluzione: lo stesso giro si riordina nel giro più corto e diventa blu.
export const Solution: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <Title name="Titolo soluzione" lines={["GiroFacile trova", "*il *giro *più *corto."]} top={290} inAt={0} outAt={2.455} />
      <Window width={960} height={700} top={500} outAt={2.5}>
        <RouteMap
          morph={tween(frame, fps, 0.3125, 1.161, 0, 1, ease.power3InOut)}
          color={tween(frame, fps, 0.536, 0.536, 0, 1, ease.power2InOut)}
          draw={1}
          stopScale={() => 1}
        />
      </Window>
      <Pill top={1150} kind="ok" inAt={1.25} outAt={2.5}>
        Per ogni furgone, in pochi minuti
      </Pill>
    </AbsoluteFill>
  );
};
