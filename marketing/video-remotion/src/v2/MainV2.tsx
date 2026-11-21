import React from "react";
import { Audio } from "@remotion/media";
import { AbsoluteFill, Sequence, staticFile } from "remotion";
import { CostoV2 } from "./CostoV2";
import { LunediMattina, MartediMattina } from "./Giro";
import { HookV2 } from "./HookV2";
import { LunediSera } from "./LunediSera";
import { OutroV2 } from "./OutroV2";
import { PrezzoV2 } from "./PrezzoV2";

// v2 "La giornata di un furgone": 900 fotogrammi (30 s, 30 fps).
// Stessa logica della v1 (gasolio → perché ora → problema → soluzione → costo → invito),
// raccontata seguendo un furgone: lunedì mattina a occhio, lunedì sera un clic, martedì mattina il giro più corto.
// Una cosa alla volta per schermata; le scene escono verso l'alto prima che entri la successiva.
export const MainV2: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#ffffff" }}>
      <Sequence name="1 Gancio" from={0} durationInFrames={90}>
        <HookV2 />
      </Sequence>
      <Sequence name="3 Lunedì mattina" from={210} durationInFrames={150}>
        <LunediMattina />
      </Sequence>
      <Sequence name="4 Lunedì sera" from={360} durationInFrames={165}>
        <LunediSera />
      </Sequence>
      <Sequence name="5 Martedì mattina" from={525} durationInFrames={135}>
        <MartediMattina />
      </Sequence>
      <Sequence name="6 Costo gasolio" from={660} durationInFrames={105}>
        <CostoV2 />
      </Sequence>
      <Sequence name="7 Outro" from={759} durationInFrames={141}>
        <OutroV2 />
      </Sequence>
      <Sequence name="2 Perché ora" from={90} durationInFrames={125}>
        <PrezzoV2 />
      </Sequence>

      {/* musica 30 s con drop sull'esplosione blu (2,7 s) + effetti */}
      <Audio src={staticFile("audio/music-v2.wav")} volume={0.8} />
      <Sequence name="sfx click è" from={10} layout="none"><Audio src={staticFile("sfx/click-soft.mp3")} volume={0.7} /></Sequence>
      <Sequence name="sfx click gasolio" from={18} layout="none"><Audio src={staticFile("sfx/click-soft.mp3")} volume={0.7} /></Sequence>
      <Sequence name="sfx click buttato" from={25} layout="none"><Audio src={staticFile("sfx/click-soft.mp3")} volume={0.7} /></Sequence>
      <Sequence name="sfx whoosh esplosione" from={69} layout="none"><Audio src={staticFile("sfx/whoosh.mp3")} volume={0.7} /></Sequence>
      <Sequence name="sfx impatto esplosione" from={79} layout="none"><Audio src={staticFile("sfx/impact-bass-1.mp3")} volume={0.9} /></Sequence>
      <Sequence name="sfx pop +31%" from={153} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.5} /></Sequence>
      <Sequence name="sfx whoosh blu via" from={195} layout="none"><Audio src={staticFile("sfx/whoosh-short.mp3")} volume={0.6} /></Sequence>
      <Sequence name="sfx pop ordine sbagliato" from={300} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.45} /></Sequence>
      <Sequence name="sfx pop orari" from={387} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.4} /></Sequence>
      <Sequence name="sfx pop ZTL" from={408} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.4} /></Sequence>
      <Sequence name="sfx pop sponda" from={429} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.4} /></Sequence>
      <Sequence name="sfx pop 3 giri" from={453} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.45} /></Sequence>
      <Sequence name="sfx whoosh furgone parte" from={555} layout="none"><Audio src={staticFile("sfx/whoosh-short.mp3")} volume={0.35} /></Sequence>
      <Sequence name="sfx pop ogni furgone" from={612} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.45} /></Sequence>
      <Sequence name="sfx pop riquadro" from={687} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.45} /></Sequence>
      <Sequence name="sfx pop 3 giri km" from={702} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.4} /></Sequence>
      <Sequence name="sfx whoosh logo" from={756} layout="none"><Audio src={staticFile("sfx/whoosh.mp3")} volume={0.7} /></Sequence>
      <Sequence name="sfx impatto logo" from={777} layout="none"><Audio src={staticFile("sfx/impact-bass-1.mp3")} volume={0.75} /></Sequence>
      <Sequence name="sfx pop tasto" from={828} layout="none"><Audio src={staticFile("sfx/pop.mp3")} volume={0.5} /></Sequence>
    </AbsoluteFill>
  );
};
