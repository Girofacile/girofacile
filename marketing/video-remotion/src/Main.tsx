import React from "react";
import { Audio } from "@remotion/media";
import { AbsoluteFill, Sequence, staticFile } from "remotion";
import { Calcolo } from "./scenes/Calcolo";
import { Costo } from "./scenes/Costo";
import { Hook } from "./scenes/Hook";
import { Outro } from "./scenes/Outro";
import { Pilastro } from "./scenes/Pilastro";
import { Problem } from "./scenes/Problem";
import { Solution } from "./scenes/Solution";
import { Stat } from "./scenes/Stat";

// Composizione principale: 750 fotogrammi (25 s, 30 fps). Le scene si sovrappongono di
// pochi fotogrammi dove un elemento esce mentre il successivo entra (come nella v4).
// Il blu della scena "perché ora" sta sopra il "problema" mentre vola via.
export const Main: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#ffffff" }}>
      <Sequence name="1 Gancio" from={0} durationInFrames={38}>
        <Hook />
      </Sequence>
      <Sequence name="3 Problema" from={131} durationInFrames={112}>
        <Problem />
      </Sequence>
      <Sequence name="4 Soluzione" from={236} durationInFrames={86}>
        <Solution />
      </Sequence>
      <Sequence name="5 Scarico ZTL sponda" from={316} durationInFrames={102}>
        <Pilastro />
      </Sequence>
      <Sequence name="6 Un clic" from={412} durationInFrames={100}>
        <Calcolo />
      </Sequence>
      <Sequence name="7 Costo gasolio" from={506} durationInFrames={110}>
        <Costo />
      </Sequence>
      <Sequence name="8 Outro" from={608} durationInFrames={142}>
        <Outro />
      </Sequence>
      <Sequence name="2 Perché ora" from={38} durationInFrames={98}>
        <Stat />
      </Sequence>

      {/* audio: musica (drop sull'esplosione blu a 1,18 s) + effetti agli stessi momenti della v4 */}
      <Audio src={staticFile("audio/music.wav")} volume={0.8} />
      <Sequence name="sfx click è" from={5} layout="none"><Audio src={staticFile("sfx/click-soft.mp3")} volume={0.7} /></Sequence>
      <Sequence name="sfx click gasolio" from={9} layout="none"><Audio src={staticFile("sfx/click-soft.mp3")} volume={0.7} /></Sequence>
      <Sequence name="sfx click buttato" from={14} layout="none"><Audio src={staticFile("sfx/click-soft.mp3")} volume={0.7} /></Sequence>
      <Sequence name="sfx whoosh esplosione" from={27} layout="none"><Audio src={staticFile("sfx/whoosh.mp3")} volume={0.7} /></Sequence>
      <Sequence name="sfx impatto esplosione" from={35} layout="none"><Audio src={staticFile("sfx/impact-bass-1.mp3")} volume={0.9} /></Sequence>
      <Sequence name="sfx pop +31%" from={83} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.5} /></Sequence>
      <Sequence name="sfx whoosh blu via" from={123} layout="none"><Audio src={staticFile("sfx/whoosh-short.mp3")} volume={0.6} /></Sequence>
      <Sequence name="sfx pop ordine sbagliato" from={175} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.45} /></Sequence>
      <Sequence name="sfx pop km gasolio" from={188} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.45} /></Sequence>
      <Sequence name="sfx whoosh riordino" from={244} layout="none"><Audio src={staticFile("sfx/whoosh-short.mp3")} volume={0.35} /></Sequence>
      <Sequence name="sfx pop ogni furgone" from={273} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.45} /></Sequence>
      <Sequence name="sfx pop fasce" from={343} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.4} /></Sequence>
      <Sequence name="sfx pop ZTL" from={352} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.4} /></Sequence>
      <Sequence name="sfx pop sponda" from={362} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.4} /></Sequence>
      <Sequence name="sfx pop 3 giri" from={439} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.45} /></Sequence>
      <Sequence name="sfx pop carburante" from={544} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.45} /></Sequence>
      <Sequence name="sfx pop km" from={553} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.4} /></Sequence>
      <Sequence name="sfx whoosh logo" from={605} layout="none"><Audio src={staticFile("sfx/whoosh.mp3")} volume={0.7} /></Sequence>
      <Sequence name="sfx impatto logo" from={624} layout="none"><Audio src={staticFile("sfx/impact-bass-1.mp3")} volume={0.75} /></Sequence>
      <Sequence name="sfx pop tasto" from={668} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.5} /></Sequence>
    </AbsoluteFill>
  );
};
