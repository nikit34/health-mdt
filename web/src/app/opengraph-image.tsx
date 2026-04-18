import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Consilium — cardiometabolic MDT";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function OGImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background:
            "radial-gradient(at 85% 20%, rgba(124, 196, 255, 0.18), transparent 60%), #0a0a0b",
          color: "#e9ebef",
          padding: "80px 96px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div
            style={{
              width: 14,
              height: 14,
              borderRadius: 9999,
              background: "#7cc4ff",
            }}
          />
          <div style={{ fontSize: 30, fontWeight: 600, letterSpacing: -0.5 }}>
            Consilium
          </div>
          <div style={{ fontSize: 22, color: "#8a8e96", marginLeft: 6 }}>
            · cardiometabolic MDT
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div
            style={{
              fontSize: 76,
              fontWeight: 600,
              lineHeight: 1.05,
              letterSpacing: -1.5,
              maxWidth: 920,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <span>Understand your</span>
            <span>
              <span style={{ color: "#7cc4ff" }}>cardiometabolic risk</span>
              <span> — сейчас.</span>
            </span>
          </div>
          <div style={{ fontSize: 28, color: "#a5a8af", maxWidth: 920, lineHeight: 1.35 }}>
            9 ИИ-специалистов + GP читают твои анализы, Apple Watch и Withings
            и выдают отчёт с 3 конкретными действиями.
          </div>
        </div>

        <div
          style={{
            display: "flex",
            gap: 16,
            alignItems: "center",
            fontSize: 22,
            color: "#8a8e96",
          }}
        >
          <div
            style={{
              padding: "10px 18px",
              borderRadius: 12,
              background: "rgba(124, 196, 255, 0.12)",
              color: "#7cc4ff",
              display: "flex",
              alignItems: "center",
              gap: 10,
            }}
          >
            <span>Первый отчёт — бесплатно</span>
          </div>
          <div>ESC · ADA · ESMO · KDIGO · RCGP</div>
        </div>
      </div>
    ),
    { ...size },
  );
}
