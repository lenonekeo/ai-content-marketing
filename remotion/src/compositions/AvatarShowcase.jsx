import {
  useCurrentFrame, useVideoConfig,
  interpolate, spring, Sequence, AbsoluteFill,
  OffthreadVideo, staticFile, Img
} from "remotion";

// ─── Brand tokens ─────────────────────────────────────────────────────────────
const BG       = "#07071a";
const B_BLUE   = "#4f8ef7";
const B_PURPLE = "#a855f7";
const B_CYAN   = "#06b6d4";
const WHITE    = "#ffffff";
const MUTED    = "#94a3b8";

function GlowOrb({ top, left, size, color, opacity = 0.12 }) {
  return (
    <div style={{
      position: "absolute", top, left, width: size, height: size, borderRadius: "50%",
      background: `radial-gradient(circle, ${color}${Math.round(opacity*255).toString(16).padStart(2,"0")} 0%, transparent 70%)`,
      pointerEvents: "none",
    }} />
  );
}

// ─── Scene 1 — Dashboard screenshot + avatar PiP (0–150f, 5s) ────────────────
function SceneDashboard() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const screenScale = spring({ frame, fps, from: 0.88, to: 1, durationInFrames: 45 });
  const screenOp    = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp" });
  const pipScale    = spring({ frame, fps, from: 0, to: 1, durationInFrames: 40, delay: 35 });
  const pipOp       = interpolate(frame, [35, 65], [0, 1], { extrapolateRight: "clamp" });
  const label1Op    = interpolate(frame, [55, 80], [0, 1], { extrapolateRight: "clamp" });
  const label1Y     = spring({ frame, fps, from: 15, to: 0, durationInFrames: 30, delay: 55 });
  const label2Op    = interpolate(frame, [80, 105], [0, 1], { extrapolateRight: "clamp" });
  const label2Y     = spring({ frame, fps, from: 15, to: 0, durationInFrames: 30, delay: 80 });
  const fadeOut     = interpolate(frame, [130, 150], [1, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: BG, opacity: fadeOut }}>
      <GlowOrb top="-10%" left="60%" size={600} color={B_BLUE} opacity={0.1} />

      {/* App screenshot — left 2/3 */}
      <div style={{
        position: "absolute", top: 60, left: 60, width: 1120, height: 680,
        borderRadius: 16, overflow: "hidden",
        boxShadow: "0 32px 80px rgba(0,0,0,0.7)",
        border: "1px solid rgba(255,255,255,0.08)",
        opacity: screenOp, transform: `scale(${screenScale})`, transformOrigin: "top left",
      }}>
        <Img src={staticFile("dashboard.png")} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "top" }} />
      </div>

      {/* Gradient overlay on screenshot edge */}
      <div style={{
        position: "absolute", top: 60, left: 900, width: 280, height: 680,
        background: `linear-gradient(90deg, transparent, ${BG})`,
        pointerEvents: "none",
      }} />

      {/* HeyGen avatar PiP — right */}
      <div style={{
        position: "absolute", right: 60, top: 100, width: 380, height: 520,
        borderRadius: 24, overflow: "hidden",
        boxShadow: `0 20px 60px rgba(79,142,247,0.5)`,
        border: `3px solid ${B_BLUE}`,
        opacity: pipOp, transform: `scale(${pipScale})`, transformOrigin: "top right",
      }}>
        <OffthreadVideo
          src={staticFile("heygen_latest.mp4")}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </div>

      {/* Labels */}
      <div style={{
        position: "absolute", bottom: 160, left: 80,
        opacity: label1Op, transform: `translateY(${label1Y}px)`,
        background: "rgba(0,0,0,0.75)", backdropFilter: "blur(12px)",
        border: `1.5px solid ${B_BLUE}`, borderRadius: 12,
        padding: "12px 24px", color: WHITE, fontSize: 20, fontWeight: 700,
        fontFamily: "'Segoe UI', Arial, sans-serif",
      }}>
        📊 Automated Approval Queue
      </div>
      <div style={{
        position: "absolute", bottom: 100, left: 80,
        opacity: label2Op, transform: `translateY(${label2Y}px)`,
        background: "rgba(0,0,0,0.75)", backdropFilter: "blur(12px)",
        border: `1.5px solid ${B_PURPLE}`, borderRadius: 12,
        padding: "12px 24px", color: WHITE, fontSize: 20, fontWeight: 700,
        fontFamily: "'Segoe UI', Arial, sans-serif",
      }}>
        🤖 AI-Generated Content — Ready to Publish
      </div>
    </AbsoluteFill>
  );
}

// ─── Scene 2 — Create page screenshot + avatar PiP (150–300f, 5s) ─────────────
function SceneCreate() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const screenOp    = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp" });
  const screenSlide = spring({ frame, fps, from: 80, to: 0, durationInFrames: 45 });
  const pipScale    = spring({ frame, fps, from: 0, to: 1, durationInFrames: 40, delay: 20 });
  const pipOp       = interpolate(frame, [20, 50], [0, 1], { extrapolateRight: "clamp" });
  const tag1Op      = interpolate(frame, [50, 70], [0, 1], { extrapolateRight: "clamp" });
  const tag2Op      = interpolate(frame, [70, 90], [0, 1], { extrapolateRight: "clamp" });
  const tag3Op      = interpolate(frame, [90, 110], [0, 1], { extrapolateRight: "clamp" });
  const fadeOut     = interpolate(frame, [130, 150], [1, 0], { extrapolateRight: "clamp" });

  const tags = [
    { label: "💬 AI Chat — Write posts in seconds",   color: B_BLUE,   op: tag1Op },
    { label: "🎬 One-click Video Generation",          color: B_PURPLE, op: tag2Op },
    { label: "📅 Multi-platform Auto-scheduling",      color: B_CYAN,   op: tag3Op },
  ];

  return (
    <AbsoluteFill style={{ background: BG, opacity: fadeOut }}>
      <GlowOrb top="20%" left="-5%" size={500} color={B_PURPLE} opacity={0.1} />

      {/* HeyGen avatar — left */}
      <div style={{
        position: "absolute", left: 60, top: 110, width: 360, height: 500,
        borderRadius: 24, overflow: "hidden",
        boxShadow: `0 20px 60px rgba(168,85,247,0.5)`,
        border: `3px solid ${B_PURPLE}`,
        opacity: pipOp, transform: `scale(${pipScale})`, transformOrigin: "top left",
      }}>
        <OffthreadVideo
          src={staticFile("heygen_latest.mp4")}
          startFrom={90}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </div>

      {/* Feature tags */}
      <div style={{
        position: "absolute", left: 460, top: 130,
        display: "flex", flexDirection: "column", gap: 20,
        fontFamily: "'Segoe UI', Arial, sans-serif",
      }}>
        {tags.map((t, i) => (
          <div key={i} style={{
            opacity: t.op,
            background: "rgba(0,0,0,0.75)", backdropFilter: "blur(12px)",
            border: `1.5px solid ${t.color}`, borderRadius: 12,
            padding: "14px 28px", color: WHITE, fontSize: 20, fontWeight: 700,
          }}>
            {t.label}
          </div>
        ))}
      </div>

      {/* App screenshot — right */}
      <div style={{
        position: "absolute", top: 60, left: 460, right: 40, height: 680,
        borderRadius: 16, overflow: "hidden",
        boxShadow: "0 32px 80px rgba(0,0,0,0.7)",
        border: "1px solid rgba(255,255,255,0.08)",
        opacity: screenOp, transform: `translateX(${screenSlide}px)`,
      }}>
        <Img src={staticFile("create.png")} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "top" }} />
      </div>

      {/* Gradient overlay on screenshot left edge */}
      <div style={{
        position: "absolute", top: 60, left: 460, width: 200, height: 680,
        background: `linear-gradient(90deg, ${BG}, transparent)`,
        pointerEvents: "none",
      }} />
    </AbsoluteFill>
  );
}

// ─── Scene 3 — CTA with avatar (300–420f, 4s) ────────────────────────────────
function SceneCTA() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const fadeIn    = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });
  const pipScale  = spring({ frame, fps, from: 0, to: 1, durationInFrames: 45, delay: 10 });
  const pipOp     = interpolate(frame, [10, 45], [0, 1], { extrapolateRight: "clamp" });
  const titleOp   = interpolate(frame, [30, 60], [0, 1], { extrapolateRight: "clamp" });
  const titleY    = spring({ frame, fps, from: 30, to: 0, durationInFrames: 40, delay: 30 });
  const subOp     = interpolate(frame, [55, 80], [0, 1], { extrapolateRight: "clamp" });
  const ctaOp     = interpolate(frame, [80, 105], [0, 1], { extrapolateRight: "clamp" });
  const ctaScale  = spring({ frame, fps, from: 0.8, to: 1, durationInFrames: 35, delay: 80 });
  const urlOp     = interpolate(frame, [105, 118], [0, 1], { extrapolateRight: "clamp" });
  const pulse     = interpolate(frame % 60, [0, 30, 60], [1, 1.03, 1]);

  return (
    <AbsoluteFill style={{ background: BG, opacity: fadeIn }}>
      <GlowOrb top="0%"  left="45%" size={700} color={B_PURPLE} opacity={0.1} />
      <GlowOrb top="50%" left="-5%" size={500} color={B_BLUE}   opacity={0.1} />

      {/* Avatar */}
      <div style={{
        position: "absolute", left: 100, top: "50%", marginTop: -280,
        width: 400, height: 560, borderRadius: 28, overflow: "hidden",
        boxShadow: `0 24px 80px rgba(79,142,247,0.4)`,
        border: `3px solid ${B_BLUE}`,
        opacity: pipOp, transform: `scale(${pipScale})`, transformOrigin: "center left",
      }}>
        <OffthreadVideo
          src={staticFile("heygen_latest.mp4")}
          startFrom={180}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </div>

      {/* Text */}
      <div style={{
        position: "absolute", left: 600, right: 80, top: "50%", marginTop: -220,
        fontFamily: "'Segoe UI', Arial, sans-serif",
      }}>
        <div style={{ opacity: titleOp, transform: `translateY(${titleY}px)`, fontSize: 68, fontWeight: 900, color: WHITE, lineHeight: 1.15, marginBottom: 20 }}>
          Automate Your Content.<br />
          <span style={{ background: `linear-gradient(90deg, ${B_BLUE}, ${B_PURPLE})`, WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            Grow Faster.
          </span>
        </div>
        <div style={{ width: 300, height: 4, borderRadius: 2, background: `linear-gradient(90deg, ${B_BLUE}, ${B_PURPLE}, ${B_CYAN})`, marginBottom: 24, opacity: titleOp }} />
        <div style={{ opacity: subOp, fontSize: 24, color: MUTED, lineHeight: 1.6, marginBottom: 36 }}>
          AI posts · Videos · Auto-scheduling<br />all in one platform.
        </div>
        <div style={{ opacity: ctaOp, transform: `scale(${ctaScale * pulse})`, display: "inline-block", marginBottom: 24 }}>
          <div style={{ background: `linear-gradient(135deg, ${B_BLUE}, ${B_PURPLE})`, borderRadius: 16, padding: "20px 52px" }}>
            <div style={{ fontSize: 26, fontWeight: 700, color: WHITE }}>Book a Free Discovery Call</div>
          </div>
        </div>
        <div style={{ opacity: urlOp, fontSize: 22, color: B_CYAN, fontWeight: 600, display: "block" }}>
          app.makone-bi.com
        </div>
      </div>
    </AbsoluteFill>
  );
}

// ─── Root ─────────────────────────────────────────────────────────────────────
export const AvatarShowcase = () => {
  return (
    <AbsoluteFill style={{ background: BG }}>
      <Sequence from={0}   durationInFrames={150}><SceneDashboard /></Sequence>
      <Sequence from={150} durationInFrames={150}><SceneCreate    /></Sequence>
      <Sequence from={300} durationInFrames={120}><SceneCTA       /></Sequence>
    </AbsoluteFill>
  );
};
