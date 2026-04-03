import { useCurrentFrame, useVideoConfig, interpolate, spring, Sequence, AbsoluteFill } from "remotion";

// ─── Brand tokens ────────────────────────────────────────────────────────────
const B_BLUE   = "#4f8ef7";
const B_PURPLE = "#a855f7";
const B_CYAN   = "#06b6d4";
const BG       = "#07071a";
const WHITE    = "#ffffff";
const MUTED    = "#94a3b8";

// ─── Defaults (used when no props passed) ────────────────────────────────────
const DEFAULT_HOOK_LINE1  = "Still doing content manually?";
const DEFAULT_HOOK_LINE2  = "There's a better way.";
const DEFAULT_PRODUCT     = "MakOne BI";
const DEFAULT_TAGLINE     = "AI-Powered Content Marketing Automation";
const DEFAULT_SUB_TEXT    = "Start automating your content today";
const DEFAULT_CTA         = "Book a Free Discovery Call";
const DEFAULT_FEATURES    = [
  { icon: "✍️", title: "AI Content Creation",       desc: "Generate LinkedIn, Facebook & Instagram posts in seconds — powered by GPT-4.",                     color: B_BLUE   },
  { icon: "🎬", title: "Automated Video Generation", desc: "HeyGen AI clones, VEO 3 cinematic clips & Remotion branded cards — no editing needed.",            color: B_PURPLE },
  { icon: "📅", title: "Smart Scheduling & Approval",desc: "Review drafts, approve or edit, then publish automatically across all your platforms.",             color: B_CYAN   },
];
const DEFAULT_STATS = [
  { value: "5+",  label: "Platforms"         },
  { value: "AI",  label: "Generated Content" },
  { value: "24/7",label: "Automated"         },
];

// ─── Shared helpers ──────────────────────────────────────────────────────────
function GlowOrb({ top, left, size, color, opacity = 0.15 }) {
  return (
    <div style={{
      position: "absolute", top, left,
      width: size, height: size, borderRadius: "50%",
      background: `radial-gradient(circle, ${color}${Math.round(opacity * 255).toString(16).padStart(2, "0")} 0%, transparent 70%)`,
      pointerEvents: "none",
    }} />
  );
}

function GradientBar({ style = {} }) {
  return (
    <div style={{
      height: 4, borderRadius: 2,
      background: `linear-gradient(90deg, ${B_BLUE}, ${B_PURPLE}, ${B_CYAN})`,
      ...style,
    }} />
  );
}

// ─── Scene 1 — Hook ───────────────────────────────────────────────────────────
function SceneHook({ hookLine1, hookLine2 }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const line1Opacity = interpolate(frame, [5, 25],  [0, 1], { extrapolateRight: "clamp" });
  const line1Y       = spring({ frame, fps, from: 30, to: 0, durationInFrames: 30, delay: 5 });
  const line2Opacity = interpolate(frame, [30, 50], [0, 1], { extrapolateRight: "clamp" });
  const line2Y       = spring({ frame, fps, from: 30, to: 0, durationInFrames: 30, delay: 30 });
  const line3Opacity = interpolate(frame, [55, 75], [0, 1], { extrapolateRight: "clamp" });
  const line3Scale   = spring({ frame, fps, from: 0.8, to: 1, durationInFrames: 30, delay: 55 });
  const fadeOut      = interpolate(frame, [75, 90], [1, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: BG, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", opacity: fadeOut }}>
      <GlowOrb top="-10%" left="60%" size={500} color={B_PURPLE} />
      <GlowOrb top="50%"  left="-5%" size={400} color={B_BLUE} />
      <div style={{ textAlign: "center", padding: "0 120px", fontFamily: "'Segoe UI', Arial, sans-serif" }}>
        <div style={{ opacity: line1Opacity, transform: `translateY(${line1Y}px)`, fontSize: 36, color: MUTED, letterSpacing: 3, textTransform: "uppercase", marginBottom: 24 }}>
          {hookLine1}
        </div>
        <div style={{ opacity: line2Opacity, transform: `translateY(${line2Y}px)`, fontSize: 64, fontWeight: 800, color: WHITE, lineHeight: 1.2, marginBottom: 32 }}>
          {hookLine2}
        </div>
        <div style={{ opacity: line3Opacity, transform: `scale(${line3Scale})` }}>
          <GradientBar style={{ width: 200, margin: "0 auto" }} />
        </div>
      </div>
    </AbsoluteFill>
  );
}

// ─── Scene 2 — Brand reveal ───────────────────────────────────────────────────
function SceneReveal({ productName, tagline }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const bgOpacity   = interpolate(frame, [0, 15],    [0, 1], { extrapolateRight: "clamp" });
  const barWidth    = interpolate(frame, [5, 40],    [0, 1920], { extrapolateRight: "clamp" });
  const nameScale   = spring({ frame, fps, from: 0.5, to: 1, durationInFrames: 45, delay: 20 });
  const nameOpacity = interpolate(frame, [20, 55],   [0, 1], { extrapolateRight: "clamp" });
  const tagOpacity  = interpolate(frame, [55, 80],   [0, 1], { extrapolateRight: "clamp" });
  const tagY        = spring({ frame, fps, from: 20, to: 0, durationInFrames: 30, delay: 55 });
  const urlOpacity  = interpolate(frame, [80, 105],  [0, 1], { extrapolateRight: "clamp" });
  const fadeOut     = interpolate(frame, [105, 120], [1, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: BG, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", opacity: bgOpacity * fadeOut }}>
      <GlowOrb top="15%" left="10%" size={600} color={B_BLUE}   opacity={0.12} />
      <GlowOrb top="40%" left="65%" size={500} color={B_PURPLE} opacity={0.14} />

      <div style={{ position: "absolute", top: 0, left: 0, height: 4, width: barWidth, background: `linear-gradient(90deg, ${B_BLUE}, ${B_PURPLE}, ${B_CYAN})` }} />

      <div style={{ textAlign: "center", fontFamily: "'Segoe UI', Arial, sans-serif", zIndex: 1 }}>
        <div style={{ fontSize: 18, fontWeight: 500, color: B_CYAN, letterSpacing: 6, textTransform: "uppercase", marginBottom: 16, opacity: nameOpacity }}>
          Introducing
        </div>
        <div style={{ fontSize: 100, fontWeight: 900, color: WHITE, letterSpacing: 4, opacity: nameOpacity, transform: `scale(${nameScale})`, lineHeight: 1 }}>
          {productName}
        </div>
        <GradientBar style={{ width: 320, margin: "24px auto 28px" }} />
        <div style={{ opacity: tagOpacity, transform: `translateY(${tagY}px)`, fontSize: 32, color: MUTED, letterSpacing: 2, fontWeight: 300 }}>
          {tagline}
        </div>
        <div style={{ opacity: urlOpacity, marginTop: 28, fontSize: 22, color: B_BLUE, fontWeight: 600, letterSpacing: 1 }}>
          app.makone-bi.com
        </div>
      </div>

      <div style={{ position: "absolute", bottom: 0, right: 0, height: 4, width: barWidth, background: `linear-gradient(270deg, ${B_BLUE}, ${B_PURPLE}, ${B_CYAN})` }} />
    </AbsoluteFill>
  );
}

// ─── Scene 3 — Features ───────────────────────────────────────────────────────
function FeatureSlide({ icon, title, desc, color }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const fadeIn    = interpolate(frame, [0, 20],  [0, 1], { extrapolateRight: "clamp" });
  const iconScale = spring({ frame, fps, from: 0, to: 1, durationInFrames: 35, delay: 5 });
  const titleY    = spring({ frame, fps, from: 40, to: 0, durationInFrames: 40, delay: 20 });
  const titleOp   = interpolate(frame, [20, 45], [0, 1], { extrapolateRight: "clamp" });
  const descOp    = interpolate(frame, [40, 65], [0, 1], { extrapolateRight: "clamp" });
  const descY     = spring({ frame, fps, from: 20, to: 0, durationInFrames: 35, delay: 40 });
  const lineW     = interpolate(frame, [30, 70], [0, 280], { extrapolateRight: "clamp" });
  const fadeOut   = interpolate(frame, [72, 90], [1, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: BG, display: "flex", alignItems: "center", justifyContent: "center", opacity: fadeIn * fadeOut }}>
      <GlowOrb top="20%" left="65%" size={500} color={color}  opacity={0.18} />
      <GlowOrb top="60%" left="-5%" size={350} color={B_BLUE} opacity={0.1} />

      <div style={{ display: "flex", alignItems: "center", gap: 80, padding: "0 120px", fontFamily: "'Segoe UI', Arial, sans-serif", maxWidth: 1600, width: "100%" }}>
        <div style={{ transform: `scale(${iconScale})`, fontSize: 120, flexShrink: 0, filter: `drop-shadow(0 0 30px ${color}66)` }}>
          {icon}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ opacity: titleOp, transform: `translateY(${titleY}px)`, fontSize: 62, fontWeight: 800, color: WHITE, lineHeight: 1.15, marginBottom: 20 }}>
            {title}
          </div>
          <div style={{ width: lineW, height: 3, background: `linear-gradient(90deg, ${color}, ${B_PURPLE})`, borderRadius: 2, marginBottom: 24 }} />
          <div style={{ opacity: descOp, transform: `translateY(${descY}px)`, fontSize: 30, color: MUTED, lineHeight: 1.6, fontWeight: 300 }}>
            {desc}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
}

function SceneFeatures({ features }) {
  const colors = [B_BLUE, B_PURPLE, B_CYAN];
  return (
    <>
      {features.map((f, i) => (
        <Sequence key={i} from={i * 90} durationInFrames={90}>
          <FeatureSlide icon={f.icon} title={f.title} desc={f.desc} color={f.color || colors[i % 3]} />
        </Sequence>
      ))}
    </>
  );
}

// ─── Scene 4 — Stats ─────────────────────────────────────────────────────────
function StatCard({ value, label, delay, color }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const scale   = spring({ frame, fps, from: 0, to: 1, durationInFrames: 40, delay });
  const opacity = interpolate(frame, [delay, delay + 25], [0, 1], { extrapolateRight: "clamp" });

  return (
    <div style={{ opacity, transform: `scale(${scale})`, textAlign: "center", flex: 1 }}>
      <div style={{ fontSize: 80, fontWeight: 900, color, lineHeight: 1, marginBottom: 10 }}>{value}</div>
      <div style={{ fontSize: 22, color: MUTED, letterSpacing: 2, textTransform: "uppercase", fontWeight: 500 }}>{label}</div>
    </div>
  );
}

function SceneStats({ stats }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fadeIn  = interpolate(frame, [0, 15],    [0, 1], { extrapolateRight: "clamp" });
  const fadeOut = interpolate(frame, [100, 120], [1, 0], { extrapolateRight: "clamp" });
  const titleOp = interpolate(frame, [5, 30],   [0, 1], { extrapolateRight: "clamp" });
  const titleY  = spring({ frame, fps, from: -20, to: 0, durationInFrames: 30, delay: 5 });
  const lineOp  = interpolate(frame, [60, 80],  [0, 1], { extrapolateRight: "clamp" });
  const colors  = [B_BLUE, B_PURPLE, B_CYAN];

  return (
    <AbsoluteFill style={{ background: BG, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", opacity: fadeIn * fadeOut }}>
      <GlowOrb top="-10%" left="30%" size={700} color={B_PURPLE} opacity={0.1} />
      <div style={{ fontFamily: "'Segoe UI', Arial, sans-serif", width: "100%", padding: "0 120px" }}>
        <div style={{ opacity: titleOp, transform: `translateY(${titleY}px)`, fontSize: 36, color: MUTED, textAlign: "center", letterSpacing: 3, textTransform: "uppercase", marginBottom: 60 }}>
          Built for Results
        </div>
        <div style={{ display: "flex", gap: 60, alignItems: "center" }}>
          {stats.map((s, i) => (
            <StatCard key={i} value={s.value} label={s.label} delay={20 + i * 20} color={colors[i % 3]} />
          ))}
        </div>
        <GradientBar style={{ width: "100%", marginTop: 60, opacity: lineOp }} />
      </div>
    </AbsoluteFill>
  );
}

// ─── Scene 5 — CTA ───────────────────────────────────────────────────────────
function SceneCTA({ ctaText, subText }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const fadeIn     = interpolate(frame, [0, 15],    [0, 1], { extrapolateRight: "clamp" });
  const subOp      = interpolate(frame, [10, 35],   [0, 1], { extrapolateRight: "clamp" });
  const subY       = spring({ frame, fps, from: -20, to: 0, durationInFrames: 30, delay: 10 });
  const titleScale = spring({ frame, fps, from: 0.7, to: 1, durationInFrames: 45, delay: 35 });
  const titleOp    = interpolate(frame, [35, 65],   [0, 1], { extrapolateRight: "clamp" });
  const ctaOp      = interpolate(frame, [70, 95],   [0, 1], { extrapolateRight: "clamp" });
  const ctaScale   = spring({ frame, fps, from: 0.85, to: 1, durationInFrames: 35, delay: 70 });
  const urlOp      = interpolate(frame, [100, 125], [0, 1], { extrapolateRight: "clamp" });
  const lineW      = interpolate(frame, [95, 135],  [0, 520], { extrapolateRight: "clamp" });
  const pulse      = interpolate(frame % 60, [0, 30, 60], [1, 1.03, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: BG, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", opacity: fadeIn }}>
      <GlowOrb top="10%" left="5%"  size={500} color={B_BLUE}   opacity={0.15} />
      <GlowOrb top="40%" left="65%" size={600} color={B_PURPLE} opacity={0.15} />

      <div style={{ textAlign: "center", padding: "0 120px", fontFamily: "'Segoe UI', Arial, sans-serif", zIndex: 1 }}>
        <div style={{ opacity: subOp, transform: `translateY(${subY}px)`, fontSize: 28, color: MUTED, letterSpacing: 4, textTransform: "uppercase", marginBottom: 20 }}>
          {subText}
        </div>
        <div style={{ opacity: titleOp, transform: `scale(${titleScale})`, fontSize: 88, fontWeight: 900, color: WHITE, lineHeight: 1.1, marginBottom: 32 }}>
          Win with AI Automation
        </div>
        <div style={{ opacity: ctaOp, transform: `scale(${ctaScale * pulse})`, display: "inline-block", background: `linear-gradient(135deg, ${B_BLUE}, ${B_PURPLE})`, borderRadius: 16, padding: "24px 64px", marginBottom: 32 }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: WHITE, letterSpacing: 1 }}>
            {ctaText}
          </div>
        </div>
        <div style={{ width: lineW, height: 3, background: `linear-gradient(90deg, ${B_BLUE}, ${B_PURPLE}, ${B_CYAN})`, borderRadius: 2, margin: "0 auto 28px" }} />
        <div style={{ opacity: urlOp, fontSize: 28, color: B_CYAN, fontWeight: 600, letterSpacing: 2 }}>
          app.makone-bi.com
        </div>
      </div>
    </AbsoluteFill>
  );
}

// ─── Root composition ─────────────────────────────────────────────────────────
export const ProductLaunch = ({
  hookLine1   = DEFAULT_HOOK_LINE1,
  hookLine2   = DEFAULT_HOOK_LINE2,
  productName = DEFAULT_PRODUCT,
  tagline     = DEFAULT_TAGLINE,
  features    = DEFAULT_FEATURES,
  stats       = DEFAULT_STATS,
  ctaText     = DEFAULT_CTA,
  subText     = DEFAULT_SUB_TEXT,
}) => {
  // Normalise features — ensure each has a color
  const colors = [B_BLUE, B_PURPLE, B_CYAN];
  const normFeatures = features.slice(0, 3).map((f, i) => ({ color: colors[i], ...f }));

  return (
    <AbsoluteFill style={{ background: BG }}>
      <Sequence from={0}   durationInFrames={90}>  <SceneHook     hookLine1={hookLine1} hookLine2={hookLine2} /></Sequence>
      <Sequence from={90}  durationInFrames={120}> <SceneReveal   productName={productName} tagline={tagline} /></Sequence>
      <Sequence from={210} durationInFrames={270}> <SceneFeatures features={normFeatures} /></Sequence>
      <Sequence from={480} durationInFrames={120}> <SceneStats    stats={stats.slice(0, 3)} /></Sequence>
      <Sequence from={600} durationInFrames={150}> <SceneCTA      ctaText={ctaText} subText={subText} /></Sequence>
    </AbsoluteFill>
  );
};
