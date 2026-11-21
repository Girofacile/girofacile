import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { BLUE, INK, TEXT, ease, tween } from "../lib/theme";

type Kind = "ok" | "no" | "warn" | "up";

const ICON: Record<Kind, { char: string; bg: string; fg: string }> = {
  ok: { char: "✓", bg: "#e4edff", fg: BLUE },
  no: { char: "✕", bg: "#ffe4e1", fg: "#d92d20" },
  warn: { char: "!", bg: "#fff1d6", fg: "#b25e00" },
  up: { char: "↑", bg: "#ffe4e1", fg: "#d92d20" },
};

/** Etichetta bianca con icona: entra con una molla senza rimbalzo. */
export const Pill: React.FC<{ top: number; kind?: Kind; inAt: number; outAt?: number; children: React.ReactNode }> = ({
  top,
  kind = "ok",
  inAt,
  outAt,
  children,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = tween(frame, fps, inAt, 0.5, 0, 1, ease.spring);
  const q = outAt === undefined ? 0 : tween(frame, fps, outAt, 0.22, 0, 1, ease.power3In);
  const ic = ICON[kind];
  return (
    <div
      style={{
        position: "absolute",
        left: "50%",
        top,
        display: "flex",
        alignItems: "center",
        gap: 14,
        whiteSpace: "nowrap",
        background: "#ffffff",
        borderRadius: 999,
        padding: "16px 30px 16px 18px",
        boxShadow: "0 12px 32px rgba(15,34,80,.16), 0 0 0 1.5px #e6eaf2",
        fontFamily: TEXT,
        fontSize: 36,
        fontWeight: 500,
        color: INK,
        zIndex: 10,
        opacity: Math.min(1, p * 1.6) * (1 - q),
        translate: `-50% ${24 * (1 - p) - 20 * q}px`,
        scale: `${0.86 + 0.14 * p}`,
      }}
    >
      <b
        style={{
          width: 44,
          height: 44,
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 26,
          fontWeight: 600,
          background: ic.bg,
          color: ic.fg,
        }}
      >
        {ic.char}
      </b>
      <span>{children}</span>
    </div>
  );
};

export const Strong: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <strong style={{ color: BLUE, fontWeight: 600 }}>{children}</strong>
);
