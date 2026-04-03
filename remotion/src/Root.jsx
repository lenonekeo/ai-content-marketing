import { Composition } from "remotion";
import { PostCard } from "./compositions/PostCard";
import { Intro } from "./compositions/Intro";
import { Outro } from "./compositions/Outro";
import { ProductLaunch } from "./compositions/ProductLaunch";
import { AvatarShowcase } from "./compositions/AvatarShowcase";

// ── PostCard: duration scales with text length (reading time) ─────────────────
const calcPostCard = ({ props }) => {
  const words = (props.text || "").split(/\s+/).filter(Boolean).length;
  // ~2.5 words/sec reading pace, min 8s, max 30s, +2s for in/out animation
  const secs = Math.min(30, Math.max(8, Math.ceil(words / 2.5) + 2));
  return { durationInFrames: secs * 30 };
};

// ── AvatarShowcase: duration = HeyGen video length + 4s CTA buffer ────────────
const calcAvatarShowcase = ({ props }) => {
  const vidSecs = props.videoDurationSecs || 14;
  // Scene 1 (5s) + Scene 2 (5s) + Scene 3 (rest of video + 4s CTA)
  const totalSecs = Math.max(14, vidSecs + 4);
  return { durationInFrames: Math.round(totalSecs * 30) };
};

// ── ProductLaunch: scales with feature count (3–5 features supported) ─────────
const calcProductLaunch = ({ props }) => {
  const featureCount = Math.min(5, Math.max(1, (props.features || []).length || 3));
  // Hook(3s) + Reveal(4s) + Features(3s each) + Stats(4s) + CTA(5s)
  const secs = 3 + 4 + featureCount * 3 + 4 + 5;
  return { durationInFrames: secs * 30 };
};

export const RemotionRoot = () => {
  return (
    <>
      {/* Social media post card — 1080x1080, duration adapts to text length */}
      <Composition
        id="PostCard"
        component={PostCard}
        calculateMetadata={calcPostCard}
        fps={30}
        width={1080}
        height={1080}
        defaultProps={{
          text: "This is a sample AI-generated post about automation.\n\nKey benefits include time savings, cost reduction, and improved accuracy across your business operations.",
          businessName: "AI Automation Co",
          website: "yourwebsite.com",
        }}
      />

      {/* YouTube branded intro — 1920x1080, fixed 3s */}
      <Composition
        id="Intro"
        component={Intro}
        durationInFrames={90}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          businessName: "AI Automation Co",
          tagline: "AI Automation Experts",
        }}
      />

      {/* YouTube branded outro — 1920x1080, fixed 6s */}
      <Composition
        id="Outro"
        component={Outro}
        durationInFrames={180}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          businessName: "AI Automation Co",
          website: "yourwebsite.com",
          ctaText: "Book a free discovery call",
        }}
      />

      {/* Product launch — 1920x1080, duration adapts to feature count */}
      <Composition
        id="ProductLaunch"
        component={ProductLaunch}
        calculateMetadata={calcProductLaunch}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          hookLine1: "Still doing content manually?",
          hookLine2: "There's a better way.",
          productName: "MakOne BI",
          tagline: "AI-Powered Content Marketing Automation",
          features: [
            { icon: "✍️", title: "AI Content Creation",        desc: "Generate LinkedIn, Facebook & Instagram posts in seconds." },
            { icon: "🎬", title: "Automated Video Generation",  desc: "HeyGen, VEO 3, and Remotion — no editing needed."         },
            { icon: "📅", title: "Smart Scheduling & Approval", desc: "Review, approve, and publish across all platforms."        },
          ],
          stats: [
            { value: "5+",  label: "Platforms"         },
            { value: "AI",  label: "Generated Content" },
            { value: "24/7",label: "Automated"         },
          ],
          ctaText: "Book a Free Discovery Call",
          subText: "Start automating your content today",
        }}
      />

      {/* Avatar + App showcase — 1920x1080, duration matches HeyGen video */}
      <Composition
        id="AvatarShowcase"
        component={AvatarShowcase}
        calculateMetadata={calcAvatarShowcase}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          videoDurationSecs: 14,
        }}
      />
    </>
  );
};
