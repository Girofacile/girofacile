import React from "react";
import { AbsoluteFill } from "remotion";
import { Pill, Strong } from "../components/Pill";
import { Title } from "../components/Title";
import { DayChip, FactRow } from "./parts";

// v2 · 4 Lunedì sera: con un clic GiroFacile prepara i giri di domani, sapendo già orari, ZTL e sponda.
export const LunediSera: React.FC = () => {
  return (
    <AbsoluteFill>
      <DayChip inAt={0.1} outAt={5.1}>Lunedì · sera</DayChip>
      <Title name="Titolo un clic" lines={["Con GiroFacile,", "*un *clic."]} top={380} inAt={0.25} outAt={5.1} />
      <FactRow top={620} inAt={0.9} outAt={5.1} kind="ok" title="Orari di scarico" sub="già nel calcolo del giro" />
      <FactRow top={800} inAt={1.6} outAt={5.13} kind="warn" title="ZTL" sub="avviso prima di partire" />
      <FactRow top={980} inAt={2.3} outAt={5.16} kind="warn" title="Sponda" sub="avviso per il mezzo" />
      <Pill top={1160} kind="ok" inAt={3.1} outAt={5.16}>
        <Strong>3 giri</Strong> pronti in pochi minuti
      </Pill>
    </AbsoluteFill>
  );
};
