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

// Scene boundaries (frames)
const S1_START = 0;
const S2_START = 150;
const S3_START = 300;
const TOTAL    = 420;

// ─── Root ─────────────────────────────────────────────────────────────────────
export const AvatarShowcase = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Scene progress (0–1 within each scene)
  const inS1 = frame >= S1_START && frame < S2_START;
  const inS2 = frame >= S2_START && frame < S3_START;
  const inS3 = frame >= S3_START;

  const f1 = Math.max(0, frame - S1_START);  // local frame in scene 1
  const f2 = Math.max(0, frame - S2_START);  // local frame in scene 2
  const f3 = Math.max(0, frame - S3_START);  // local frame in scene 3

  // ── Avatar position/size animated across scenes ──────────────────────────
  // Scene 1: PiP top-right (380×520)
  // Scene 2: left panel (360×500)
  // Scene 3: large left (400×560)

  const avatarRight  = inS1 ? 60  : undefined;
  const avatarLeft   = inS1 ? undefined : (inS2 ? 60 : 100);
  const avatarTop    = inS1 ? 100 : (inS2 ? 110 : "auto");
  const avatarMarginTop = inS3 ? -280 : undefined;
  const avatarTopPct    = inS3 ? "50%" : undefined;

  const avatarW = inS1 ? 380 : (inS2 ? 360 : 400);
  const avatarH = inS1 ? 520 : (inS2 ? 500 : 560);

  const avatarBorder = inS1 ? B_BLUE : (inS2 ? B_PURPLE : B_BLUE);

  // ── Scene 1 animations ───────────────────────────────────────────────────
  const s1_screenScale = spring({ frame: f1, fps, from: 0.88, to: 1, durationInFrames: 45 });
  const s1_screenOp   = interpolate(f1, [0, 20], [0, 1], { extrapolateRight: "clamp" });
  const s1_pipScale   = spring({ frame: f1, fps, from: 0, to: 1, durationInFrames: 40, delay: 35 });
  const s1_pipOp      = interpolate(f1, [35, 65], [0, 1], { extrapolateRight: "clamp" });
  const s1_label1Op   = interpolate(f1, [55, 80], [0, 1], { extrapolateRight: "clamp" });
  const s1_label1Y    = spring({ frame: f1, fps, from: 15, to: 0, durationInFrames: 30, delay: 55 });
  const s1_label2Op   = interpolate(f1, [80, 105], [0, 1], { extrapolateRight: "clamp" });
  const s1_label2Y    = spring({ frame: f1, fps, from: 15, to: 0, durationInFrames: 30, delay: 80 });
  const s1_fadeOut    = interpolate(f1, [130, 150], [1, 0], { extrapolateRight: "clamp" });

  // ── Scene 2 animations ───────────────────────────────────────────────────
  const s2_screenOp    = interpolate(f2, [0, 20], [0, 1], { extrapolateRight: "clamp" });
  const s2_screenSlide = spring({ frame: f2, fps, from: 80, to: 0, durationInFrames: 45 });
  const s2_pipScale    = spring({ frame: f2, fps, from: 0, to: 1, durationInFrames: 40, delay: 20 });
  const s2_pipOp       = interpolate(f2, [20, 50], [0, 1], { extrapolateRight: "clamp" });
  const s2_tag1Op      = interpolate(f2, [50, 70], [0, 1], { extrapolateRight: "clamp" });
  const s2_tag2Op      = interpolate(f2, [70, 90], [0, 1], { extrapolateRight: "clamp" });
  const s2_tag3Op      = interpolate(f2, [90, 110], [0, 1], { extrapolateRight: "clamp" });
  const s2_fadeOut     = interpolate(f2, [130, 150], [1, 0], { extrapolateRight: "clamp" });

  // ── Scene 3 animations ───────────────────────────────────────────────────
  const s3_fadeIn   = interpolate(f3, [0, 15], [0, 1], { extrapolateRight: "clamp" });
  const s3_pipScale = spring({ frame: f3, fps, from: 0, to: 1, durationInFrames: 45, delay: 10 });
  const s3_pipOp    = interpolate(f3, [10, 45], [0, 1], { extrapolateRight: "clamp" });
  const s3_titleOp  = interpolate(f3, [30, 60], [0, 1], { extrapolateRight: "clamp" });
  const s3_titleY   = spring({ frame: f3, fps, from: 30, to: 0, durationInFrames: 40, delay: 30 });
  const s3_subOp    = interpolate(f3, [55, 80], [0, 1], { extrapolateRight: "clamp" });
  const s3_ctaOp    = interpolate(f3, [80, 105], [0, 1], { extrapolateRight: "clamp" });
  const s3_ctaScale = spring({ frame: f3, fps, from: 0.8, to: 1, durationInFrames: 35, delay: 80 });
  const s3_urlOp    = interpolate(f3, [105, 118], [0, 1], { extrapolateRight: "clamp" });
  const s3_pulse    = interpolate(f3 % 60, [0, 30, 60], [1, 1.03, 1]);

  // Avatar scale/opacity per scene
  const avatarScale = inS1 ? s1_pipScale : (inS2 ? s2_pipScale : s3_pipScale);
  const avatarOp    = inS1 ? s1_pipOp   : (inS2 ? s2_pipOp   : s3_pipOp);
  const avatarOrigin = inS1 ? "top right" : (inS2 ? "top left" : "center left");

  const tags = [
    { label: "💬 AI Chat — Write posts in seconds",   color: B_BLUE,   op: s2_tag1Op },
    { label: "🎬 One-click Video Generation",          color: B_PURPLE, op: s2_tag2Op },
    { label: "📅 Multi-platform Auto-scheduling",      color: B_CYAN,   op: s2_tag3Op },
  ];

  return (
    <AbsoluteFill style={{ background: BG }}>

      {/* ── Single continuous avatar video — no restarts, no audio overlap ── */}
      <div style={{
        position: "absolute",
        right:     avatarRight,
        left:      avatarLeft,
        top:       avatarTopPct ?? avatarTop,
        marginTop: avatarMarginTop,
        width:  avatarW,
        height: avatarH,
        borderRadius: 24,
        overflow: "hidden",
        boxShadow: `0 20px 60px rgba(79,142,247,0.5)`,
        border: `3px solid ${avatarBorder}`,
        opacity: avatarOp,
        transform: `scale(${avatarScale})`,
        transformOrigin: avatarOrigin,
        zIndex: 10,
        transition: "all 0.3s ease",
      }}>
        <OffthreadVideo
          src={staticFile("heygen_latest.mp4")}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </div>

      {/* ══ SCENE 1 — Dashboard + avatar PiP ══════════════════════════════ */}
      <Sequence from={S1_START} durationInFrames={S2_START - S1_START}>
        <AbsoluteFill style={{ opacity: s1_fadeOut }}>
          <GlowOrb top="-10%" left="60%" size={600} color={B_BLUE} opacity={0.1} />

          {/* App screenshot */}
          <div style={{
            position: "absolute", top: 60, left: 60, width: 1120, height: 680,
            borderRadius: 16, overflow: "hidden",
            boxShadow: "0 32px 80px rgba(0,0,0,0.7)",
            border: "1px solid rgba(255,255,255,0.08)",
            opacity: s1_screenOp,
            transform: `scale(${s1_screenScale})`,
            transformOrigin: "top left",
          }}>
            <Img src={staticFile("dashboard.png")} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "top" }} />
          </div>

          {/* Gradient overlay */}
          <div style={{
            position: "absolute", top: 60, left: 900, width: 280, height: 680,
            background: `linear-gradient(90deg, transparent, ${BG})`,
            pointerEvents: "none",
          }} />

          {/* Labels */}
          <div style={{
            position: "absolute", bottom: 160, left: 80,
            opacity: s1_label1Op, transform: `translateY(${s1_label1Y}px)`,
            background: "rgba(0,0,0,0.75)", backdropFilter: "blur(12px)",
            border: `1.5px solid ${B_BLUE}`, borderRadius: 12,
            padding: "12px 24px", color: WHITE, fontSize: 20, fontWeight: 700,
            fontFamily: "'Segoe UI', Arial, sans-serif",
          }}>
            📊 Automated Approval Queue
          </div>
          <div style={{
            position: "absolute", bottom: 100, left: 80,
            opacity: s1_label2Op, transform: `translateY(${s1_label2Y}px)`,
            background: "rgba(0,0,0,0.75)", backdropFilter: "blur(12px)",
            border: `1.5px solid ${B_PURPLE}`, borderRadius: 12,
            padding: "12px 24px", color: WHITE, fontSize: 20, fontWeight: 700,
            fontFamily: "'Segoe UI', Arial, sans-serif",
          }}>
            🤖 AI-Generated Content — Ready to Publish
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* ══ SCENE 2 — Create page + feature tags ══════════════════════════ */}
      <Sequence from={S2_START} durationInFrames={S3_START - S2_START}>
        <AbsoluteFill style={{ opacity: s2_fadeOut }}>
          <GlowOrb top="20%" left="-5%" size={500} color={B_PURPLE} opacity={0.1} />

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
            opacity: s2_screenOp,
            transform: `translateX(${s2_screenSlide}px)`,
          }}>
            <Img src={staticFile("create.png")} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "top" }} />
          </div>

          {/* Gradient overlay */}
          <div style={{
            position: "absolute", top: 60, left: 460, width: 200, height: 680,
            background: `linear-gradient(90deg, ${BG}, transparent)`,
            pointerEvents: "none",
          }} />
        </AbsoluteFill>
      </Sequence>

      {/* ══ SCENE 3 — CTA ═════════════════════════════════════════════════ */}
      <Sequence from={S3_START} durationInFrames={TOTAL - S3_START}>
        <AbsoluteFill style={{ opacity: s3_fadeIn }}>
          <GlowOrb top="0%"  left="45%" size={700} color={B_PURPLE} opacity={0.1} />
          <GlowOrb top="50%" left="-5%" size={500} color={B_BLUE}   opacity={0.1} />

          {/* Text right of avatar */}
          <div style={{
            position: "absolute", left: 600, right: 80, top: "50%", marginTop: -220,
            fontFamily: "'Segoe UI', Arial, sans-serif",
          }}>
            <div style={{
              opacity: s3_titleOp,
              transform: `translateY(${s3_titleY}px)`,
              fontSize: 68, fontWeight: 900, color: WHITE, lineHeight: 1.15, marginBottom: 20,
            }}>
              Automate Your Content.<br />
              <span style={{ background: `linear-gradient(90deg, ${B_BLUE}, ${B_PURPLE})`, WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                Grow Faster.
              </span>
            </div>
            <div style={{ width: 300, height: 4, borderRadius: 2, background: `linear-gradient(90deg, ${B_BLUE}, ${B_PURPLE}, ${B_CYAN})`, marginBottom: 24, opacity: s3_titleOp }} />
            <div style={{ opacity: s3_subOp, fontSize: 24, color: MUTED, lineHeight: 1.6, marginBottom: 36 }}>
              AI posts · Videos · Auto-scheduling<br />all in one platform.
            </div>
            <div style={{ opacity: s3_ctaOp, transform: `scale(${s3_ctaScale * s3_pulse})`, display: "inline-block", marginBottom: 24 }}>
              <div style={{ background: `linear-gradient(135deg, ${B_BLUE}, ${B_PURPLE})`, borderRadius: 16, padding: "20px 52px" }}>
                <div style={{ fontSize: 26, fontWeight: 700, color: WHITE }}>Book a Free Discovery Call</div>
              </div>
            </div>
            <div style={{ opacity: s3_urlOp, fontSize: 22, color: B_CYAN, fontWeight: 600, display: "block" }}>
              app.makone-bi.com
            </div>
          </div>
        </AbsoluteFill>
      </Sequence>

    </AbsoluteFill>
  );
};
