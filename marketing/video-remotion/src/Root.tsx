import React from "react";
import { Composition, Folder } from "remotion";
import "./lib/fonts";
import { Main } from "./Main";
import { Calcolo } from "./scenes/Calcolo";
import { Costo } from "./scenes/Costo";
import { Hook } from "./scenes/Hook";
import { Outro } from "./scenes/Outro";
import { Pilastro } from "./scenes/Pilastro";
import { Problem } from "./scenes/Problem";
import { Solution } from "./scenes/Solution";
import { Stat } from "./scenes/Stat";
import { CostoV2 } from "./v2/CostoV2";
import { LunediMattina, MartediMattina } from "./v2/Giro";
import { HookV2 } from "./v2/HookV2";
import { LunediSera } from "./v2/LunediSera";
import { MainV2 } from "./v2/MainV2";
import { OutroV2 } from "./v2/OutroV2";
import { PrezzoV2 } from "./v2/PrezzoV2";

// Reel 9:16 campagna carburante (TOFU). Una composizione per scena + la principale.
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Folder name="Scene">
        <Composition id="Gancio" component={Hook} width={1080} height={1920} fps={30} durationInFrames={38} />
        <Composition id="PercheOra" component={Stat} width={1080} height={1920} fps={30} durationInFrames={98} />
        <Composition id="Problema" component={Problem} width={1080} height={1920} fps={30} durationInFrames={112} />
        <Composition id="Soluzione" component={Solution} width={1080} height={1920} fps={30} durationInFrames={86} />
        <Composition id="ScaricoZtlSponda" component={Pilastro} width={1080} height={1920} fps={30} durationInFrames={102} />
        <Composition id="UnClic" component={Calcolo} width={1080} height={1920} fps={30} durationInFrames={100} />
        <Composition id="CostoGasolio" component={Costo} width={1080} height={1920} fps={30} durationInFrames={110} />
        <Composition id="Outro" component={Outro} width={1080} height={1920} fps={30} durationInFrames={142} />
      </Folder>
      <Composition id="GiroFacileCarburante" component={Main} width={1080} height={1920} fps={30} durationInFrames={750} />
      <Folder name="Scene-v2-giornata">
        <Composition id="V2Gancio" component={HookV2} width={1080} height={1920} fps={30} durationInFrames={90} />
        <Composition id="V2PercheOra" component={PrezzoV2} width={1080} height={1920} fps={30} durationInFrames={125} />
        <Composition id="V2LunediMattina" component={LunediMattina} width={1080} height={1920} fps={30} durationInFrames={150} />
        <Composition id="V2LunediSera" component={LunediSera} width={1080} height={1920} fps={30} durationInFrames={165} />
        <Composition id="V2MartediMattina" component={MartediMattina} width={1080} height={1920} fps={30} durationInFrames={135} />
        <Composition id="V2CostoGasolio" component={CostoV2} width={1080} height={1920} fps={30} durationInFrames={105} />
        <Composition id="V2Outro" component={OutroV2} width={1080} height={1920} fps={30} durationInFrames={141} />
      </Folder>
      <Composition id="GiroFacileCarburanteV2" component={MainV2} width={1080} height={1920} fps={30} durationInFrames={900} />
    </>
  );
};
