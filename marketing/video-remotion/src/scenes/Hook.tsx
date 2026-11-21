import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Accent } from "../components/Title";
import { BLUE, DISPLAY, NAVY, ease, tween } from "../lib/theme";

// 1 · Gancio: "Ogni km in più è gasolio buttato." leggibile dal primo frame,
// le parole della seconda riga sbattono a ritmo, "gasolio" si gonfia e dalla sua "o" esplode il blu.
export const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // parole della seconda riga che "sbattono" (scala 1.9 -> 1, a tempo con i click)
  const slam = (t: number) => {
    const p = tween(frame, fps, t, 0.196, 0, 1, ease.expoOut);
    return { opacity: p, scale: `${1.9 - 0.9 * p}`, filter: `blur(${10 * (1 - p)}px)` };
  };
  // le parole non chiave spariscono quando gasolio si gonfia
  const fade = tween(frame, fps, 0.893, 0.223, 0, 1, ease.power3In);
  const gone = { opacity: 1 - fade, filter: `blur(${12 * fade}px)`, scale: `${1 - 0.2 * fade}` };

  const hl = tween(frame, fps, 0.402, 0.268, 0, 1, ease.power3Out);
  const swell = tween(frame, fps, 0.848, 0.3125, 1, 1.25, ease.power2In);
  const flood = tween(frame, fps, 0.893, 0.339, 0, 16, ease.expoIn);

  const word: React.CSSProperties = { display: "inline-block", position: "relative" };
  return (
    <AbsoluteFill style={{ backgroundColor: "#ffffff" }}>
      <div
        style={{
          position: "absolute",
          left: 40,
          right: 40,
          top: 590,
          textAlign: "center",
          fontFamily: DISPLAY,
          fontWeight: 700,
          fontSize: 118,
          letterSpacing: "-0.025em",
          lineHeight: 1.06,
          color: NAVY,
          scale: `${tween(frame, fps, 0, 0.893, 1.08, 1, ease.power2Out)}`,
        }}
      >
        <div style={{ whiteSpace: "nowrap", ...gone }}>Ogni km in più</div>
        <div style={{ whiteSpace: "nowrap" }}>
          <span style={{ ...word, ...slam(0.161) }}>
            <span style={{ ...word, ...gone }}>è</span>
          </span>{" "}
          <span style={{ ...word, ...slam(0.286), zIndex: 5 }}>
            <span style={{ ...word, scale: `${swell}` }}>
              <Accent hl={hl}>
                gasoli
                <span style={{ position: "relative" }}>
                  o
                  <span
                    style={{
                      position: "absolute",
                      left: "50%",
                      top: "58%",
                      width: 200,
                      height: 200,
                      margin: "-100px 0 0 -100px",
                      borderRadius: "50%",
                      background: BLUE,
                      scale: `${flood}`,
                      zIndex: 30,
                    }}
                  />
                </span>
              </Accent>
            </span>
          </span>{" "}
          <span style={{ ...word, ...slam(0.464) }}>
            <span style={{ ...word, ...gone }}>buttato.</span>
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
