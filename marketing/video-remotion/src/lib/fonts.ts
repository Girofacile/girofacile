import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";

export const fontsReady = Promise.all([
  loadFont({ family: "Bricolage Grotesque", url: staticFile("fonts/bricolage-grotesque-latin-700-normal.woff2"), weight: "700" }),
  loadFont({ family: "IBM Plex Sans", url: staticFile("fonts/ibm-plex-sans-latin-500-normal.woff2"), weight: "500" }),
  loadFont({ family: "IBM Plex Sans", url: staticFile("fonts/ibm-plex-sans-latin-600-normal.woff2"), weight: "600" }),
]);
