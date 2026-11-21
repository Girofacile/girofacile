import { Easing, interpolate } from "remotion";

// Palette approvata (marketing/video/CLAUDE.md)
export const BLUE = "#1665ff";
export const NAVY = "#0f2250";
export const INK = "#16213a";
export const MUTED = "#5a6680";
export const HIGHLIGHT = "#e4edff";
export const DISPLAY = "Bricolage Grotesque";
export const TEXT = "IBM Plex Sans";

// Il video v4 era scritto in "tempo base" e accelerato di 1.12.
// Qui tutti i tempi sono già in secondi reali, relativi all'inizio della scena.
export const ease = {
  expoOut: Easing.bezier(0.16, 1, 0.3, 1),
  expoIn: Easing.bezier(0.7, 0, 0.84, 0),
  expoInOut: Easing.bezier(0.87, 0, 0.13, 1),
  power3In: Easing.bezier(0.32, 0, 0.67, 0),
  power3Out: Easing.bezier(0.33, 1, 0.68, 1),
  power3InOut: Easing.bezier(0.65, 0, 0.35, 1),
  power2InOut: Easing.bezier(0.45, 0, 0.55, 1),
  power2Out: Easing.bezier(0.5, 1, 0.89, 1),
  power2In: Easing.bezier(0.11, 0, 0.5, 0),
  power1InOut: Easing.bezier(0.37, 0, 0.63, 1),
  sineInOut: Easing.bezier(0.37, 0, 0.63, 1),
  // molla senza rimbalzo
  spring: Easing.spring({ damping: 200 }),
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** Interpola tra due valori dentro una finestra [start, start+dur] in secondi. */
export const tween = (
  frame: number,
  fps: number,
  start: number,
  dur: number,
  from: number,
  to: number,
  easing: (t: number) => number = ease.expoOut,
) => interpolate(frame, [start * fps, (start + dur) * fps], [from, to], { ...clamp, easing });
