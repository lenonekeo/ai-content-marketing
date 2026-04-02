import { Composition } from "remotion";
import { PostCard } from "./compositions/PostCard";
import { Intro } from "./compositions/Intro";
import { Outro } from "./compositions/Outro";

export const RemotionRoot = () => {
  return (
    <>
      {/* Social media post card — 1080x1080 square, 8 seconds */}
      <Composition
        id="PostCard"
        component={PostCard}
        durationInFrames={240}
        fps={30}
        width={1080}
        height={1080}
        defaultProps={{
          text: "This is a sample AI-generated post about automation.\n\nKey benefits include time savings, cost reduction, and improved accuracy across your business operations.",
          businessName: "AI Automation Co",
          website: "yourwebsite.com",
        }}
      />

      {/* YouTube branded intro — 1920x1080, 3 seconds */}
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

      {/* YouTube branded outro — 1920x1080, 6 seconds */}
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
    </>
  );
};
