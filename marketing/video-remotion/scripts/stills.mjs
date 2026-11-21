// Esporta fotogrammi di controllo: node scripts/stills.mjs 0 95 200 ...
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import path from "node:path";
const browserExecutable = process.env.REMOTION_BROWSER || null;
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts") });
const composition = await selectComposition({ serveUrl, id: "GiroFacileCarburante", browserExecutable });
for (const f of process.argv.slice(2).map(Number)) {
  await renderStill({ serveUrl, composition, frame: f, output: `out/stills/f${String(f).padStart(3, "0")}.png`, browserExecutable, scale: 0.5 });
  console.log("still", f);
}
