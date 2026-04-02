import {
  useCurrentFrame, useVideoConfig,
  interpolate, spring, Sequence, AbsoluteFill, Video
} from "remotion";

// ─── Brand tokens ─────────────────────────────────────────────────────────────
const BG       = "#07071a";
const NAV_BG   = "#0d0d2b";
const B_BLUE   = "#4f8ef7";
const B_PURPLE = "#a855f7";
const B_CYAN   = "#06b6d4";
const B_GREEN  = "#22c55e";
const WHITE    = "#ffffff";
const MUTED    = "#94a3b8";
const CARD_BG  = "#f1f5f9";
const CARD_BD  = "#e2e8f0";

// ─── Helpers ──────────────────────────────────────────────────────────────────
function GlowOrb({ top, left, size, color, opacity = 0.12 }) {
  return (
    <div style={{
      position: "absolute", top, left, width: size, height: size,
      borderRadius: "50%",
      background: `radial-gradient(circle, ${color}${Math.round(opacity * 255).toString(16).padStart(2,"0")} 0%, transparent 70%)`,
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

// ─── App mockup — Nav bar ─────────────────────────────────────────────────────
function AppNav({ activeTab = "Dashboard" }) {
  const tabs = ["Dashboard", "Create", "Setup", "Content Influence", "Calendar"];
  return (
    <div style={{
      background: "#0a0a1f", height: 52, display: "flex", alignItems: "center",
      padding: "0 28px", gap: 4, borderBottom: "1px solid #1e1e3f",
    }}>
      <div style={{ color: WHITE, fontWeight: 800, fontSize: 18, marginRight: 24, letterSpacing: 1 }}>
        MakOne <span style={{ color: B_CYAN }}>BI</span>
      </div>
      {tabs.map(t => (
        <div key={t} style={{
          padding: "6px 16px", borderRadius: 6, fontSize: 13, fontWeight: 600,
          color: t === activeTab ? WHITE : MUTED,
          background: t === activeTab ? B_BLUE : "transparent",
          cursor: "pointer",
        }}>{t}</div>
      ))}
    </div>
  );
}

// ─── App mockup — Dashboard ───────────────────────────────────────────────────
const DRAFTS = [
  { type: "Educational",       industry: "E-commerce",           date: "2026-03-23" },
  { type: "Problem Solution",  industry: "Healthcare",           date: "2026-03-22" },
  { type: "Success Story",     industry: "Professional Services", date: "2026-03-20" },
  { type: "Service Highlight", industry: "Healthcare",           date: "2026-03-17" },
];

function DashboardMockup({ visibleRows = 4 }) {
  return (
    <div style={{ flex: 1, background: "#f8fafc", padding: "28px 36px", overflowY: "hidden", fontFamily: "'Segoe UI', Arial, sans-serif" }}>
      <div style={{ fontSize: 22, fontWeight: 700, color: "#1e293b", marginBottom: 4 }}>Dashboard</div>
      <div style={{ fontSize: 13, color: MUTED, marginBottom: 24 }}>AI Content Marketing — MakOne Business Intelligence</div>
      <div style={{ background: WHITE, borderRadius: 12, border: `1px solid ${CARD_BD}`, overflow: "hidden" }}>
        <div style={{ padding: "14px 20px", fontSize: 11, fontWeight: 700, color: MUTED, letterSpacing: 2, borderBottom: `1px solid ${CARD_BD}` }}>
          PENDING APPROVAL
        </div>
        {DRAFTS.slice(0, visibleRows).map((d, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", padding: "14px 20px",
            borderBottom: i < visibleRows - 1 ? `1px solid ${CARD_BD}` : "none",
          }}>
            <div style={{ flex: 1 }}>
              <span style={{ fontWeight: 600, color: "#1e293b", fontSize: 14 }}>{d.type}</span>
              <span style={{ marginLeft: 8, background: "#fef3c7", color: "#92400e", padding: "2px 8px", borderRadius: 99, fontSize: 11, fontWeight: 600 }}>Pending</span>
              <div style={{ fontSize: 12, color: MUTED, marginTop: 3 }}>{d.industry} · {d.date}</div>
            </div>
            <div style={{ background: B_GREEN, color: WHITE, padding: "8px 18px", borderRadius: 8, fontSize: 12, fontWeight: 700 }}>
              Review &amp; Approve
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── App mockup — Create page ─────────────────────────────────────────────────
function CreateMockup() {
  return (
    <div style={{ flex: 1, background: "#f8fafc", padding: "28px 36px", fontFamily: "'Segoe UI', Arial, sans-serif" }}>
      <div style={{ fontSize: 22, fontWeight: 700, color: "#1e293b", marginBottom: 4 }}>Create Content</div>
      <div style={{ fontSize: 13, color: MUTED, marginBottom: 20 }}>Chat with AI to craft your post.</div>

      {/* Settings card */}
      <div style={{ background: WHITE, borderRadius: 12, border: `1px solid ${CARD_BD}`, padding: "16px 20px", marginBottom: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: MUTED, letterSpacing: 2, marginBottom: 12 }}>SETTINGS</div>
        <div style={{ fontSize: 12, color: MUTED, marginBottom: 8 }}>Platforms</div>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          {["LinkedIn", "Facebook", "Instagram", "YouTube"].map((p, i) => (
            <div key={p} style={{
              padding: "5px 14px", borderRadius: 20, fontSize: 12, fontWeight: 600,
              border: `1.5px solid ${i < 2 ? B_BLUE : CARD_BD}`,
              color: i < 2 ? B_BLUE : MUTED,
            }}>{p}</div>
          ))}
        </div>
        <div style={{ background: "#f0fdf4", border: "1px solid #86efac", borderRadius: 8, padding: "8px 12px", fontSize: 11, color: "#166534" }}>
          ✓ Content Influence active · Topics: AI automation, AI Agents, Workflow Optimization
        </div>
      </div>

      {/* Chat card */}
      <div style={{ background: WHITE, borderRadius: 12, border: `1px solid ${CARD_BD}`, padding: "16px 20px" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: MUTED, letterSpacing: 2, marginBottom: 12 }}>CHAT</div>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
          <div style={{ width: 32, height: 32, borderRadius: "50%", background: "#1e293b", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, color: WHITE, fontWeight: 700, flexShrink: 0 }}>AI</div>
          <div style={{ background: "#f8fafc", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#334155", lineHeight: 1.5 }}>
            Hello! I'm ready to help you create great social media content. Tell me what you'd like to post about.
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Scene 1 — Dashboard spotlight (0–150f, 5s) ───────────────────────────────
function SceneDashboard({ heygenUrl }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const appFadeIn   = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp" });
  const appScale    = spring({ frame, fps, from: 0.92, to: 1, durationInFrames: 40 });
  const labelOp     = interpolate(frame, [25, 50], [0, 1], { extrapolateRight: "clamp" });
  const labelY      = spring({ frame, fps, from: 20, to: 0, durationInFrames: 30, delay: 25 });
  const pipOp       = interpolate(frame, [40, 70], [0, 1], { extrapolateRight: "clamp" });
  const pipScale    = spring({ frame, fps, from: 0, to: 1, durationInFrames: 40, delay: 40 });
  const arrowOp     = interpolate(frame, [80, 100], [0, 1], { extrapolateRight: "clamp" });
  const fadeOut     = interpolate(frame, [135, 150], [1, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: BG, opacity: fadeOut }}>
      <GlowOrb top="-5%" left="70%" size={400} color={B_BLUE} />

      {/* App window */}
      <div style={{
        position: "absolute", top: 80, left: 60, right: 420,
        borderRadius: 16, overflow: "hidden", boxShadow: "0 24px 80px rgba(0,0,0,0.6)",
        opacity: appFadeIn, transform: `scale(${appScale})`, transformOrigin: "top left",
        fontFamily: "'Segoe UI', Arial, sans-serif",
      }}>
        <AppNav activeTab="Dashboard" />
        <DashboardMockup visibleRows={4} />
      </div>

      {/* Label */}
      <div style={{
        position: "absolute", top: 86, left: 60,
        opacity: labelOp, transform: `translateY(${labelY}px)`,
        background: B_BLUE, color: WHITE, padding: "6px 16px",
        borderRadius: 99, fontSize: 14, fontWeight: 700, letterSpacing: 1,
      }}>
        📊 Dashboard — Approval Queue
      </div>

      {/* Arrow callout */}
      <div style={{
        position: "absolute", right: 430, top: 220,
        opacity: arrowOp, fontSize: 28, color: B_GREEN,
      }}>→</div>

      {/* HeyGen PiP */}
      <div style={{
        position: "absolute", right: 60, top: 120, width: 340, height: 420,
        borderRadius: 20, overflow: "hidden", boxShadow: "0 12px 60px rgba(79,142,247,0.4)",
        border: `3px solid ${B_BLUE}`,
        opacity: pipOp, transform: `scale(${pipScale})`, transformOrigin: "top right",
      }}>
        {heygenUrl ? (
          <Video src={heygenUrl} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <div style={{ width: "100%", height: "100%", background: "#111", display: "flex", alignItems: "center", justifyContent: "center", color: MUTED, fontSize: 13 }}>
            AI Avatar
          </div>
        )}
      </div>

      {/* PiP label */}
      <div style={{
        position: "absolute", right: 60, bottom: 220,
        opacity: pipOp, background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)",
        color: WHITE, padding: "6px 14px", borderRadius: 8, fontSize: 13, fontWeight: 600,
      }}>
        🤖 AI-Generated Video
      </div>
    </AbsoluteFill>
  );
}

// ─── Scene 2 — Create page spotlight (150–300f, 5s) ──────────────────────────
function SceneCreate({ heygenUrl }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const appFadeIn = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp" });
  const appSlide  = spring({ frame, fps, from: -60, to: 0, durationInFrames: 40 });
  const pipOp     = interpolate(frame, [15, 40], [0, 1], { extrapolateRight: "clamp" });
  const pipScale  = spring({ frame, fps, from: 0, to: 1, durationInFrames: 35, delay: 15 });
  const tag1Op    = interpolate(frame, [50, 70], [0, 1], { extrapolateRight: "clamp" });
  const tag2Op    = interpolate(frame, [70, 90], [0, 1], { extrapolateRight: "clamp" });
  const tag3Op    = interpolate(frame, [90, 110], [0, 1], { extrapolateRight: "clamp" });
  const fadeOut   = interpolate(frame, [135, 150], [1, 0], { extrapolateRight: "clamp" });

  const tags = [
    { label: "💬 AI Chat Content", color: B_BLUE,   top: 140 },
    { label: "🎬 Video Generation", color: B_PURPLE, top: 200 },
    { label: "📅 Auto-Schedule",    color: B_CYAN,   top: 260 },
  ];
  const tagOps = [tag1Op, tag2Op, tag3Op];

  return (
    <AbsoluteFill style={{ background: BG, opacity: fadeOut }}>
      <GlowOrb top="30%" left="-5%" size={500} color={B_PURPLE} />

      {/* HeyGen PiP — left side */}
      <div style={{
        position: "absolute", left: 60, top: 120, width: 320, height: 400,
        borderRadius: 20, overflow: "hidden", boxShadow: "0 12px 60px rgba(168,85,247,0.4)",
        border: `3px solid ${B_PURPLE}`,
        opacity: pipOp, transform: `scale(${pipScale})`, transformOrigin: "top left",
      }}>
        {heygenUrl ? (
          <Video src={heygenUrl} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <div style={{ width: "100%", height: "100%", background: "#111", display: "flex", alignItems: "center", justifyContent: "center", color: MUTED, fontSize: 13 }}>AI Avatar</div>
        )}
      </div>

      {/* Feature tags beside avatar */}
      {tags.map((t, i) => (
        <div key={i} style={{
          position: "absolute", left: 400, top: t.top,
          opacity: tagOps[i], background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)",
          border: `1.5px solid ${t.color}`, color: WHITE,
          padding: "8px 20px", borderRadius: 99, fontSize: 15, fontWeight: 600,
        }}>
          {t.label}
        </div>
      ))}

      {/* App window — right side */}
      <div style={{
        position: "absolute", top: 80, left: 580, right: 40,
        borderRadius: 16, overflow: "hidden", boxShadow: "0 24px 80px rgba(0,0,0,0.6)",
        opacity: appFadeIn, transform: `translateX(${appSlide}px)`,
        fontFamily: "'Segoe UI', Arial, sans-serif",
      }}>
        <AppNav activeTab="Create" />
        <CreateMockup />
      </div>
    </AbsoluteFill>
  );
}

// ─── Scene 3 — CTA (300–420f, 4s) ────────────────────────────────────────────
function SceneCTA({ heygenUrl }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const fadeIn    = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });
  const titleOp   = interpolate(frame, [10, 40], [0, 1], { extrapolateRight: "clamp" });
  const titleY    = spring({ frame, fps, from: 30, to: 0, durationInFrames: 40, delay: 10 });
  const subOp     = interpolate(frame, [40, 65], [0, 1], { extrapolateRight: "clamp" });
  const ctaOp     = interpolate(frame, [65, 90], [0, 1], { extrapolateRight: "clamp" });
  const ctaScale  = spring({ frame, fps, from: 0.8, to: 1, durationInFrames: 35, delay: 65 });
  const urlOp     = interpolate(frame, [90, 115], [0, 1], { extrapolateRight: "clamp" });
  const pipOp     = interpolate(frame, [20, 50], [0, 1], { extrapolateRight: "clamp" });
  const pipScale  = spring({ frame, fps, from: 0, to: 1, durationInFrames: 40, delay: 20 });
  const pulse     = interpolate(frame % 60, [0, 30, 60], [1, 1.03, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: BG, opacity: fadeIn }}>
      <GlowOrb top="0%" left="50%" size={800} color={B_PURPLE} opacity={0.1} />
      <GlowOrb top="50%" left="0%" size={500} color={B_BLUE} opacity={0.1} />

      {/* HeyGen avatar — left */}
      <div style={{
        position: "absolute", left: 100, top: "50%", transform: `translateY(-50%) scale(${pipScale})`,
        width: 360, height: 450, borderRadius: 24, overflow: "hidden",
        boxShadow: "0 24px 80px rgba(79,142,247,0.3)", border: `3px solid ${B_BLUE}`,
        opacity: pipOp, transformOrigin: "center left",
      }}>
        {heygenUrl ? (
          <Video src={heygenUrl} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <div style={{ width: "100%", height: "100%", background: "#111", display: "flex", alignItems: "center", justifyContent: "center", color: MUTED, fontSize: 13 }}>AI Avatar</div>
        )}
      </div>

      {/* Text — right */}
      <div style={{
        position: "absolute", left: 560, right: 80, top: "50%", transform: "translateY(-50%)",
        fontFamily: "'Segoe UI', Arial, sans-serif",
      }}>
        <div style={{ opacity: titleOp, transform: `translateY(${titleY}px)`, fontSize: 62, fontWeight: 900, color: WHITE, lineHeight: 1.15, marginBottom: 16 }}>
          Automate Your Content.<br />
          <span style={{ background: `linear-gradient(90deg, ${B_BLUE}, ${B_PURPLE})`, WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            Grow Faster.
          </span>
        </div>
        <GradientBar style={{ width: 280, marginBottom: 20 }} />
        <div style={{ opacity: subOp, fontSize: 22, color: MUTED, lineHeight: 1.6, marginBottom: 32 }}>
          AI-powered posts, videos &amp; scheduling —<br />all in one platform.
        </div>
        <div style={{ opacity: ctaOp, transform: `scale(${ctaScale * pulse})`, display: "inline-block" }}>
          <div style={{
            background: `linear-gradient(135deg, ${B_BLUE}, ${B_PURPLE})`,
            borderRadius: 14, padding: "18px 48px",
          }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: WHITE }}>Book a Free Discovery Call</div>
          </div>
        </div>
        <div style={{ opacity: urlOp, marginTop: 24, fontSize: 20, color: B_CYAN, fontWeight: 600 }}>
          app.makone-bi.com
        </div>
      </div>
    </AbsoluteFill>
  );
}

// ─── Root composition ─────────────────────────────────────────────────────────
export const AvatarShowcase = ({ heygenUrl = "" }) => {
  return (
    <AbsoluteFill style={{ background: BG }}>
      {/* Scene 1: Dashboard + PiP   0–150  (5s) */}
      <Sequence from={0}   durationInFrames={150}><SceneDashboard heygenUrl={heygenUrl} /></Sequence>
      {/* Scene 2: Create page + PiP 150–300 (5s) */}
      <Sequence from={150} durationInFrames={150}><SceneCreate    heygenUrl={heygenUrl} /></Sequence>
      {/* Scene 3: CTA               300–420 (4s) */}
      <Sequence from={300} durationInFrames={120}><SceneCTA       heygenUrl={heygenUrl} /></Sequence>
    </AbsoluteFill>
  );
};
