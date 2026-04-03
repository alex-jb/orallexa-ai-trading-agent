import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Orallexa — AI-Powered Capital Intelligence Engine";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#0A0A0F",
          position: "relative",
        }}
      >
        {/* Top gold accent line */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: 3,
            background: "linear-gradient(90deg, transparent 10%, #D4AF37 30%, #FFD700 50%, #C5A255 70%, transparent 90%)",
          }}
        />

        {/* Corner ornaments — top left */}
        <div style={{ position: "absolute", top: 24, left: 24, display: "flex", flexDirection: "column" }}>
          <div style={{ width: 40, height: 3, background: "#D4AF37", opacity: 0.5 }} />
          <div style={{ width: 3, height: 40, background: "#D4AF37", opacity: 0.5 }} />
        </div>
        {/* Corner ornaments — top right */}
        <div style={{ position: "absolute", top: 24, right: 24, display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
          <div style={{ width: 40, height: 3, background: "#D4AF37", opacity: 0.5 }} />
          <div style={{ width: 3, height: 40, background: "#D4AF37", opacity: 0.5, alignSelf: "flex-end" }} />
        </div>
        {/* Corner ornaments — bottom left */}
        <div style={{ position: "absolute", bottom: 24, left: 24, display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
          <div style={{ width: 3, height: 40, background: "#D4AF37", opacity: 0.5 }} />
          <div style={{ width: 40, height: 3, background: "#D4AF37", opacity: 0.5 }} />
        </div>
        {/* Corner ornaments — bottom right */}
        <div style={{ position: "absolute", bottom: 24, right: 24, display: "flex", flexDirection: "column", alignItems: "flex-end", justifyContent: "flex-end" }}>
          <div style={{ width: 3, height: 40, background: "#D4AF37", opacity: 0.5, alignSelf: "flex-end" }} />
          <div style={{ width: 40, height: 3, background: "#D4AF37", opacity: 0.5 }} />
        </div>

        {/* Brand name */}
        <div
          style={{
            fontSize: 72,
            fontWeight: 400,
            letterSpacing: "0.2em",
            background: "linear-gradient(135deg, #D4AF37, #FFD700, #C5A255)",
            backgroundClip: "text",
            color: "transparent",
            marginBottom: 16,
          }}
        >
          ORALLEXA
        </div>

        {/* Art Deco decorative rule — three diamonds */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
          <div style={{ width: 120, height: 1, background: "linear-gradient(90deg, transparent, #D4AF37)" }} />
          <div style={{ width: 8, height: 8, background: "#D4AF37", transform: "rotate(45deg)", opacity: 0.6 }} />
          <div style={{ width: 12, height: 12, border: "2px solid #D4AF37", transform: "rotate(45deg)", opacity: 0.8 }} />
          <div style={{ width: 8, height: 8, background: "#D4AF37", transform: "rotate(45deg)", opacity: 0.6 }} />
          <div style={{ width: 120, height: 1, background: "linear-gradient(270deg, transparent, #D4AF37)" }} />
        </div>

        {/* Subtitle */}
        <div
          style={{
            fontSize: 24,
            fontWeight: 300,
            letterSpacing: "0.28em",
            color: "#8B8E96",
            textTransform: "uppercase",
          }}
        >
          Capital Intelligence System
        </div>

        {/* Tagline */}
        <div
          style={{
            fontSize: 14,
            fontWeight: 300,
            color: "#F5E6CA",
            opacity: 0.5,
            marginTop: 32,
            letterSpacing: "0.06em",
          }}
        >
          9 ML Models &middot; Adversarial Debate &middot; One-Click Execution
        </div>

        {/* Bottom gold accent line */}
        <div
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            height: 3,
            background: "linear-gradient(90deg, transparent 10%, #D4AF37 30%, #FFD700 50%, #C5A255 70%, transparent 90%)",
          }}
        />
      </div>
    ),
    {
      ...size,
    }
  );
}
