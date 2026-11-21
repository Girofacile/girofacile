import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { ease, tween } from "../lib/theme";

/** Finestra stile browser (tre pallini) che entra dal basso e esce verso l'alto. */
export const Window: React.FC<{
  width: number;
  height: number;
  top: number;
  inAt?: number;
  outAt?: number;
  bar?: boolean;
  left?: number;
  children: React.ReactNode;
}> = ({ width, height, top, inAt, outAt, bar = true, left, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = inAt === undefined ? 1 : tween(frame, fps, inAt, 0.67, 0, 1, ease.expoOut);
  const q = outAt === undefined ? 0 : tween(frame, fps, outAt, 0.31, 0, 1, ease.power3In);
  return (
    <div
      style={{
        position: "absolute",
        left: left ?? 540 - width / 2,
        top,
        width,
        height,
        background: "#ffffff",
        borderRadius: bar ? 28 : 24,
        overflow: "hidden",
        boxShadow: "0 24px 70px rgba(15,34,80,.16), 0 0 0 1.5px #e6eaf2",
        opacity: p * (1 - q),
        translate: `0px ${140 * (1 - p) - 60 * q}px`,
        scale: `${(0.94 + 0.06 * p) * (1 - 0.04 * q)}`,
        filter: `blur(${8 * (1 - p) + 10 * q}px)`,
      }}
    >
      {bar ? (
        <div style={{ height: 54, background: "#f6f8fc", borderBottom: "1.5px solid #e6eaf2", display: "flex", gap: 12, alignItems: "center", paddingLeft: 24 }}>
          <i style={{ width: 16, height: 16, borderRadius: "50%", background: "#ff5f57", display: "block" }} />
          <i style={{ width: 16, height: 16, borderRadius: "50%", background: "#febc2e", display: "block" }} />
          <i style={{ width: 16, height: 16, borderRadius: "50%", background: "#28c840", display: "block" }} />
        </div>
      ) : null}
      <div style={{ position: "relative", overflow: "hidden", height: bar ? height - 54 : height }}>{children}</div>
    </div>
  );
};
