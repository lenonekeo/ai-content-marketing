import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

const BRAND_BLUE = "#4f8ef7";
const BRAND_PURPLE = "#a855f7";
const BG_DARK = "#0a0a1a";
const TEXT_PRIMARY = "#ffffff";
const TEXT_MUTED = "#94a3b8";

function stripHashtags(text) {
  return text
    .replace(/#\w+/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export const PostCard = ({ text = "", businessName = "Your Business", website = "" }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const cleanText = stripHashtags(text);
  const fontSize = cleanText.length > 500 ? 20 : cleanText.length > 300 ? 24 : 28;

  // Animation values
  const bgOpacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });

  const accentLineWidth = interpolate(frame, [5, 35], [0, 200], { extrapolateRight: "clamp" });

  const headerY = spring({ frame, fps, from: -40, to: 0, durationInFrames: 35, delay: 8 });
  const headerOpacity = interpolate(frame, [8, 30], [0, 1], { extrapolateRight: "clamp" });

  const textOpacity = interpolate(frame, [45, 80], [0, 1], { extrapolateRight: "clamp" });
  const textY = spring({ frame, fps, from: 20, to: 0, durationInFrames: 40, delay: 45 });

  const footerOpacity = interpolate(frame, [90, 115], [0, 1], { extrapolateRight: "clamp" });

  // Subtle pulse on the accent dot
  const dotScale = interpolate(
    frame % 90,
    [0, 45, 90],
    [1, 1.15, 1],
    { extrapolateRight: "clamp" }
  );

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        background: `linear-gradient(135deg, ${BG_DARK} 0%, #0d0d2b 55%, #111827 100%)`,
        display: "flex",
        flexDirection: "column",
        padding: 64,
        fontFamily: "'Segoe UI', Arial, sans-serif",
        opacity: bgOpacity,
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Background glow */}
      <div
        style={{
          position: "absolute",
          top: -200,
          right: -200,
          width: 600,
          height: 600,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${BRAND_PURPLE}18 0%, transparent 70%)`,
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: -150,
          left: -150,
          width: 500,
          height: 500,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${BRAND_BLUE}12 0%, transparent 70%)`,
          pointerEvents: "none",
        }}
      />

      {/* Header: accent line + business name */}
      <div style={{ opacity: headerOpacity, transform: `translateY(${headerY}px)` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 36 }}>
          {/* Animated accent line */}
          <div
            style={{
              width: accentLineWidth,
              height: 3,
              background: `linear-gradient(90deg, ${BRAND_BLUE}, ${BRAND_PURPLE})`,
              borderRadius: 2,
            }}
          />
          {/* Pulsing dot */}
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: BRAND_PURPLE,
              transform: `scale(${dotScale})`,
            }}
          />
        </div>

        <div
          style={{
            fontSize: 28,
            fontWeight: 700,
            color: TEXT_PRIMARY,
            letterSpacing: 1.5,
            textTransform: "uppercase",
          }}
        >
          {businessName}
        </div>
      </div>

      {/* Divider */}
      <div
        style={{
          width: "100%",
          height: 1,
          background: `linear-gradient(90deg, ${BRAND_BLUE}40, transparent)`,
          marginBottom: 36,
          opacity: headerOpacity,
        }}
      />

      {/* Post text */}
      <div
        style={{
          flex: 1,
          opacity: textOpacity,
          transform: `translateY(${textY}px)`,
          overflow: "hidden",
        }}
      >
        <p
          style={{
            fontSize,
            lineHeight: 1.7,
            color: TEXT_PRIMARY,
            margin: 0,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {cleanText}
        </p>
      </div>

      {/* Footer */}
      <div
        style={{
          opacity: footerOpacity,
          borderTop: `1px solid ${BRAND_BLUE}30`,
          paddingTop: 24,
          marginTop: 24,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span style={{ color: BRAND_BLUE, fontSize: 20, fontWeight: 600 }}>
          {website}
        </span>
        <div
          style={{
            display: "flex",
            gap: 8,
            alignItems: "center",
          }}
        >
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: BRAND_BLUE }} />
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: BRAND_PURPLE }} />
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: BRAND_BLUE }} />
        </div>
      </div>
    </div>
  );
};
