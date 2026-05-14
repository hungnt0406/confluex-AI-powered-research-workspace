/* global React, ReactDOM, TopNav, Hero, VideoSection, Sources, Pipeline, Sample, Pricing, Footer */
/* global TweaksPanel, TweakSection, TweakRadio, useTweaks */

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "headline": "grounded",
  "rhythm": "alternating"
}/*EDITMODE-END*/;

const CHAT_URL = "https://confluex.vercel.app/chat";

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  return (
    <React.Fragment>
      <TopNav chatUrl={CHAT_URL} />
      <main>
        <Hero chatUrl={CHAT_URL} headline={t.headline} />
        <VideoSection />
        <Sources />
        <Pipeline />
        <Sample />
        <Pricing />
        <Footer chatUrl={CHAT_URL} />
      </main>

      <TweaksPanel title="Tweaks">
        <TweakSection label="Hero" />
        <TweakRadio
          label="Headline"
          value={t.headline}
          options={["grounded", "evening", "canon"]}
          onChange={(v) => setTweak("headline", v)}
        />
      </TweaksPanel>
    </React.Fragment>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
