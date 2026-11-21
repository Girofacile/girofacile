import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Pill } from "../components/Pill";
import { Title } from "../components/Title";
import { Window } from "../components/Window";
import { ease, tween } from "../lib/theme";
import { DayChip, VanMap } from "./parts";

// v2 · 3 Lunedì mattina: il furgone fa il giro "a occhio" (fermate in ordine sbagliato, strade vere).
export const LunediMattina: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <DayChip inAt={0.1} outAt={4.6}>Lunedì · 6:30</DayChip>
      <Title name="Titolo a occhio" lines={["Il giro si fa", "*a *occhio."]} top={380} inAt={0.25} outAt={4.6} />
      <Window width={960} height={655} top={590} inAt={0.4} outAt={4.62}>
        <VanMap which="mess" stopsIn={tween(frame, fps, 0.7, 0.6, 0, 1, ease.power1InOut)} progress={tween(frame, fps, 1.3, 2.7, 0, 1, ease.power1InOut)} offsetY={-20} />
      </Window>
      <Pill top={1150} kind="no" inAt={3.0} outAt={4.6}>
        Fermate nell&apos;ordine sbagliato
      </Pill>
    </AbsoluteFill>
  );
};

// v2 · 5 Martedì mattina: stesso furgone, il giro più corto calcolato da GiroFacile.
export const MartediMattina: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <DayChip inAt={0.1} outAt={4.2}>Martedì · 6:30</DayChip>
      <Title name="Titolo giro corto" lines={["Stesso furgone.", "*Il *giro *più *corto."]} top={380} inAt={0.25} outAt={4.2} />
      <Window width={960} height={655} top={590} inAt={0.4} outAt={4.22}>
        <VanMap which="opt" stopsIn={tween(frame, fps, 0.6, 0.4, 0, 1, ease.power1InOut)} progress={tween(frame, fps, 1.0, 2.0, 0, 1, ease.power1InOut)} offsetY={-20} />
      </Window>
      <Pill top={1150} kind="ok" inAt={2.9} outAt={4.2}>
        Per ogni furgone, in pochi minuti
      </Pill>
    </AbsoluteFill>
  );
};
