import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { BLUE, DISPLAY, HIGHLIGHT, MUTED, NAVY, TEXT, ease, tween } from "../lib/theme";

type Variant = "dark" | "light" | "sub";

/** Parola chiave in blu con l'evidenziatore sotto (scaleX = hl). */
export const Accent: React.FC<{ children: React.ReactNode; hl?: number; variant?: Variant }> = ({ children, hl = 1, variant = "dark" }) => (
  <span style={{ position: "relative", isolation: "isolate", color: variant === "light" ? "#ffffff" : BLUE, fontWeight: variant === "sub" ? 600 : undefined }}>
    {variant === "dark" ? (
      <span
        style={{
          position: "absolute",
          left: -4,
          right: -4,
          bottom: "6%",
          height: "30%",
          background: HIGHLIGHT,
          zIndex: -1,
          transformOrigin: "0 50%",
          scale: `${hl} 1`,
        }}
      />
    ) : null}
    {children}
  </span>
);

/**
 * Titolo a righe: le parole salgono una per una con blur (entrata) e salgono via (uscita).
 * `*parola` = parola chiave in blu. Tempi in secondi reali relativi alla scena.
 */
export const Title: React.FC<{
  lines: string[];
  top: number;
  size?: number;
  inAt: number;
  outAt?: number;
  variant?: Variant;
  name: string;
}> = ({ lines, top, size = 84, inAt, outAt, variant = "dark", name }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  let i = 0;
  const sub = variant === "sub";
  return (
    <div
      data-name={name}
      style={{
        position: "absolute",
        left: 60,
        right: 60,
        top,
        textAlign: "center",
        fontFamily: sub ? TEXT : DISPLAY,
        fontWeight: sub ? 500 : 700,
        fontSize: size,
        letterSpacing: sub ? 0 : "-0.025em",
        lineHeight: 1.06,
        color: variant === "light" ? "#ffffff" : sub ? MUTED : NAVY,
      }}
    >
      {lines.map((ln, li) => (
        <div key={li} style={{ whiteSpace: "nowrap" }}>
          {ln.split(" ").map((w, wi) => {
            const k = i++;
            const acc = w.startsWith("*");
            const word = w.replace(/^\*/, "");
            const tIn = inAt + k * 0.0625;
            const tOut = outAt === undefined ? 1e9 : outAt + k * 0.027;
            const p = tween(frame, fps, tIn, 0.446, 0, 1, ease.expoOut);
            const q = tween(frame, fps, tOut, 0.25, 0, 1, ease.power3In);
            return (
              <React.Fragment key={wi}>
                {wi > 0 ? " " : null}
                <span
                  style={{
                    display: "inline-block",
                    position: "relative",
                    opacity: p * (1 - q),
                    translate: `0px ${46 * (1 - p) - 30 * q}px`,
                    filter: `blur(${10 * (1 - p) + 10 * q}px)`,
                  }}
                >
                  {acc ? <Accent variant={variant}>{word}</Accent> : word}
                </span>
              </React.Fragment>
            );
          })}
        </div>
      ))}
    </div>
  );
};
