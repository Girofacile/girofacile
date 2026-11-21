import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Pill } from "../components/Pill";
import { RouteMap } from "../components/RouteMap";
import { Title } from "../components/Title";
import { Window } from "../components/Window";
import { ease, tween } from "../lib/theme";

// 3 · Problema: il giro fatto "a occhio", con le fermate in ordine sbagliato, su strade vere.
export const Problem: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <Title name="Titolo problema" lines={["E i giri? Ancora", "*a *occhio."]} top={290} inAt={0.045} outAt={3.259} />
      <Window width={960} height={700} top={500} inAt={0.134}>
        <RouteMap
          morph={0}
          color={0}
          draw={tween(frame, fps, 0.491, 1.161, 0, 1, ease.power1InOut)}
          stopScale={(i) => tween(frame, fps, 0.357 + i * 0.0357, 0.3125, 0, 1, ease.spring)}
        />
      </Window>
      <Pill top={1060} kind="no" inAt={1.473} outAt={3.259}>
        Fermate nell&apos;ordine sbagliato
      </Pill>
      <Pill top={1160} kind="no" inAt={1.875} outAt={3.304}>
        Km e gasolio che nessuno vede
      </Pill>
    </AbsoluteFill>
  );
};
