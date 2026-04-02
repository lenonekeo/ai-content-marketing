import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

const BRAND_BLUE = "#4f8ef7";
const BRAND_PURPLE = "#a855f7";
const BG_DARK = "#0a0a1a";

export const Outro = ({
  businessName = "Your Business",
  website = "",
  ctaText = "Book a free discovery call",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const bgOpacity = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp" });

  // "Thank you" line fades in first
  const thanksOpacity = interpolate(frame, [10, 35], [0, 1], { extrapolateRight: "clamp" });
  const thanksY = spring({ frame, fps, from: -20, to: 0, durationInFrames: 30, delay: 10 });

  // Business name springs in
  const nameScale = spring({ frame, fps, from: 0.7, to: 1, durationInFrames: 40, delay: 40 });
  const nameOpacity = interpolate(frame, [40, 65], [0, 1], { extrapolateRight: "clamp" });

  // CTA text fades in
  const ctaOpacity = interpolate(frame, [75, 100], [0, 1], { extrapolateRight: "clamp" });
  const ctaY = spring({ frame, fps, from: 15, to: 0, durationInFrames: 30, delay: 75 });

  // CTA underline animates width
  const ctaLineWidth = interpolate(frame, [100, 130], [0, 500], { extrapolateRight: "clamp" });

  // Website fades in last
  const websiteOpacity = interpolate(frame, [120, 150], [0, 1], { extrapolateRight: "clamp" });

  // Subtle fade out at end
  const containerOpacity =
    frame > 160 ? interpolate(frame, [160, 180], [1, 0], { extrapolateRight: "clamp" }) : bgOpacity;

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
        opacity: containerOpacity,
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Glow orbs */}
      <div
        style={{
          position: "absolute",
          top: "10%",
          right: "10%",
          width: 500,
          height: 500,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${BRAND_PURPLE}18 0%, transparent 70%)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: "10%",
          left: "10%",
          width: 400,
          height: 400,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${BRAND_BLUE}15 0%, transparent 70%)`,
        }}
      />

      {/* Top accent bar */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 4,
          background: `linear-gradient(90deg, ${BRAND_BLUE}, ${BRAND_PURPLE}, ${BRAND_BLUE})`,
        }}
      />

      {/* Content */}
      <div style={{ textAlign: "center", zIndex: 1, padding: "0 80px" }}>
        {/* Thank you */}
        <div
          style={{
            fontSize: 32,
            fontWeight: 300,
            color: "#94a3b8",
            letterSpacing: 6,
            textTransform: "uppercase",
            opacity: thanksOpacity,
            transform: `translateY(${thanksY}px)`,
            marginBottom: 32,
          }}
        >
          Thank you for watching
        </div>

        {/* Business name */}
        <div
          style={{
            fontSize: 80,
            fontWeight: 800,
            color: "#ffffff",
            letterSpacing: 2,
            textTransform: "uppercase",
            opacity: nameOpacity,
            transform: `scale(${nameScale})`,
            lineHeight: 1.1,
            marginBottom: 12,
          }}
        >
          {businessName}
        </div>

        {/* Gradient divider */}
        <div
          style={{
            width: 280,
            height: 3,
            background: `linear-gradient(90deg, ${BRAND_BLUE}, ${BRAND_PURPLE})`,
            borderRadius: 2,
            margin: "0 auto 40px",
            opacity: nameOpacity,
          }}
        />

        {/* CTA text */}
        <div
          style={{
            opacity: ctaOpacity,
            transform: `translateY(${ctaY}px)`,
          }}
        >
          <div
            style={{
              fontSize: 36,
              fontWeight: 600,
              color: BRAND_BLUE,
              marginBottom: 8,
            }}
          >
            {ctaText}
          </div>

          {/* Animated underline */}
          <div
            style={{
              width: ctaLineWidth,
              maxWidth: "100%",
              height: 2,
              background: `linear-gradient(90deg, ${BRAND_BLUE}, ${BRAND_PURPLE})`,
              borderRadius: 1,
              margin: "0 auto 32px",
            }}
          />
        </div>

        {/* Website */}
        <div
          style={{
            fontSize: 28,
            fontWeight: 500,
            color: "#ffffff",
            opacity: websiteOpacity,
            letterSpacing: 1,
          }}
        >
          {website}
        </div>
      </div>

      {/* Bottom accent bar */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: 4,
          background: `linear-gradient(90deg, ${BRAND_PURPLE}, ${BRAND_BLUE}, ${BRAND_PURPLE})`,
        }}
      />
    </div>
  );
};
