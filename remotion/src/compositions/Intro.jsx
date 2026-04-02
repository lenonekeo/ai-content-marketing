import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

const BRAND_BLUE = "#4f8ef7";
const BRAND_PURPLE = "#a855f7";
const BG_DARK = "#0a0a1a";

export const Intro = ({ businessName = "Your Business", tagline = "AI Automation Experts" }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const bgOpacity = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp" });

  // Horizontal bar wipe from left
  const barWidth = interpolate(frame, [5, 30], [0, 1920], { extrapolateRight: "clamp" });

  // Business name: scale + opacity spring
  const nameScale = spring({ frame, fps, from: 0.6, to: 1, durationInFrames: 40, delay: 20 });
  const nameOpacity = interpolate(frame, [20, 45], [0, 1], { extrapolateRight: "clamp" });

  // Tagline fades in after name
  const taglineOpacity = interpolate(frame, [50, 75], [0, 1], { extrapolateRight: "clamp" });
  const taglineY = spring({ frame, fps, from: 15, to: 0, durationInFrames: 30, delay: 50 });

  // Bottom accent line grows
  const accentWidth = interpolate(frame, [40, 70], [0, 300], { extrapolateRight: "clamp" });

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        background: `linear-gradient(160deg, ${BG_DARK} 0%, #0d0d2b 60%, #0f111a 100%)`,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "'Segoe UI', Arial, sans-serif",
        opacity: bgOpacity,
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Animated top bar wipe */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          height: 4,
          width: barWidth,
          background: `linear-gradient(90deg, ${BRAND_BLUE}, ${BRAND_PURPLE})`,
        }}
      />

      {/* Background glow orbs */}
      <div
        style={{
          position: "absolute",
          top: "20%",
          left: "15%",
          width: 400,
          height: 400,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${BRAND_BLUE}15 0%, transparent 70%)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: "20%",
          right: "15%",
          width: 350,
          height: 350,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${BRAND_PURPLE}15 0%, transparent 70%)`,
        }}
      />

      {/* Content */}
      <div style={{ textAlign: "center", zIndex: 1 }}>
        {/* Business name */}
        <div
          style={{
            fontSize: 96,
            fontWeight: 800,
            color: "#ffffff",
            letterSpacing: 3,
            textTransform: "uppercase",
            opacity: nameOpacity,
            transform: `scale(${nameScale})`,
            lineHeight: 1.1,
          }}
        >
          {businessName}
        </div>

        {/* Accent line under name */}
        <div
          style={{
            width: accentWidth,
            height: 4,
            background: `linear-gradient(90deg, ${BRAND_BLUE}, ${BRAND_PURPLE})`,
            borderRadius: 2,
            margin: "20px auto 24px",
          }}
        />

        {/* Tagline */}
        <div
          style={{
            fontSize: 36,
            fontWeight: 400,
            color: BRAND_BLUE,
            letterSpacing: 4,
            textTransform: "uppercase",
            opacity: taglineOpacity,
            transform: `translateY(${taglineY}px)`,
          }}
        >
          {tagline}
        </div>
      </div>

      {/* Bottom bar wipe */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          right: 0,
          height: 4,
          width: barWidth,
          background: `linear-gradient(270deg, ${BRAND_BLUE}, ${BRAND_PURPLE})`,
        }}
      />
    </div>
  );
};
