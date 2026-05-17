"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/* ── Types ─────────────────────────────────────────────── */

interface FeatureCard {
  icon: string;
  title: string;
  body: string;
}

interface WelcomeStep {
  kind: "welcome";
  eyebrow: string;
  title: string;
  body: string;
  primary: string;
  secondary: string;
  featureCards?: FeatureCard[];
}

interface SpotlightStep {
  kind?: "spotlight";
  target: string;
  title: string;
  body: string;
  placement: "top" | "bottom" | "left" | "right";
  pad: number;
  radius: number;
}

type TourStep = WelcomeStep | SpotlightStep;

interface OnboardingTourProps {
  variant: "chat" | "writer";
}

/* ── Step definitions ──────────────────────────────────── */

const CHAT_STEPS: TourStep[] = [
  {
    kind: "welcome",
    eyebrow: "Welcome to Confluex",
    title: "Your AI research partner across 225M papers.",
    body: "Take a 60-second tour to learn how to chat with the literature, ground answers in real sources, and bring your own PDFs into a project.",
    primary: "Start tour",
    secondary: "Skip",
    featureCards: [
      { icon: "travel_explore", title: "Grounded chat", body: "Every answer ties back to a real paper or web source." },
      { icon: "upload_file", title: "Drop your PDFs", body: "Add your own references to the project context." },
      { icon: "graph_3", title: "Citation graph", body: "See how sources connect — and where to dig next." },
    ],
  },
  {
    target: "#ob-new",
    title: "Start a new research thread",
    body: "Every topic lives in its own project. Click <b>New Research</b> any time you want a fresh chat with its own history, papers, and citations.",
    placement: "right",
    pad: 6,
    radius: 12,
  },
  {
    target: "#ob-recents",
    title: "Pick up where you left off",
    body: "Your past projects sit under <b>Recents</b>. Selecting one re-opens its chat, its selected papers, and the context panel — exactly as you left it.",
    placement: "right",
    pad: 6,
    radius: 12,
  },
  {
    target: "#ob-writer",
    title: "When you're ready, write it",
    body: "<b>Writer Workspace</b> is the other half of Confluex. It takes the papers you've gathered here and helps you actually draft — IMRaD outline, agent-asked questions that ground every section, inline citations, and a one-click export to <b>.tex + .bib</b>. Open it from any project once you have a few sources in play.",
    placement: "right",
    pad: 6,
    radius: 12,
  },
  {
    target: "#ob-textarea",
    title: "Describe your topic, or ask a grounded question",
    body: 'Type a research question — or paste a messy idea. I\'ll expand it into search queries, surface relevant papers, and answer with citations. Press <span class="ob-kbd">Enter</span> to send, <span class="ob-kbd">Shift</span>+<span class="ob-kbd">Enter</span> for a new line.',
    placement: "top",
    pad: 10,
    radius: 12,
  },
  {
    target: "#ob-upload",
    title: "Bring your own PDF",
    body: "Tap the <b>+</b> to attach a paper from your machine. It gets parsed, added to the project, and becomes a first-class source — quoted and cited like anything from the index.",
    placement: "top",
    pad: 8,
    radius: 12,
  },
  {
    target: "#ob-mode",
    title: "Pick the right depth",
    body: "Three modes, one composer: <b>Standard</b> for fast grounded Q&amp;A, <b>Deep Search</b> for multi-step web + paper synthesis, and <b>Deep Research Max</b> for adaptive multi-round investigations (~5× credits).",
    placement: "top",
    pad: 8,
    radius: 14,
  },
  {
    target: "#ob-context",
    title: "Your sources, always in view",
    body: "The right panel keeps the papers and web citations the agent is using. Toggle a paper to include or exclude it from the next answer — your context, your control.",
    placement: "left",
    pad: 0,
    radius: 0,
  },
  {
    kind: "welcome",
    eyebrow: "You're ready",
    title: "Pose your first question.",
    body: "Open a topic in the composer or pick a suggestion. You can re-launch this tour any time from the help icon in the bottom corner.",
    primary: "Start researching",
    secondary: "Back",
  },
];

const WRITER_STEPS: TourStep[] = [
  {
    kind: "welcome",
    eyebrow: "Welcome to Writer",
    title: "Turn your research into a manuscript — one section at a time.",
    body: "Writer is the second half of Confluex: it takes the papers from your research chat and helps you actually write. Outline, draft, cite, and export to LaTeX. Here's how it works.",
    primary: "Start tour",
    secondary: "Skip",
    featureCards: [
      { icon: "format_list_numbered", title: "Outline-first", body: "IMRaD scaffold, statuses, progress at a glance." },
      { icon: "help", title: "Agent asks, you answer", body: "Inputs flow straight into the right subsection." },
      { icon: "code", title: ".tex + .bib export", body: "Drop into Overleaf or arXiv — ready as-is." },
    ],
  },
  {
    target: "#ob-titlebox",
    title: "One document, one structure",
    body: "Name your manuscript and pick a structure (IMRaD). Writer auto-saves continuously — no save button, no lost work.",
    placement: "bottom",
    pad: 8,
    radius: 12,
  },
  {
    target: "#ob-outline",
    title: "Outline & progress, always visible",
    body: "Every section gets a status: <b>Pending</b>, <b>Drafted</b>, <b>Edited</b>, <b>Awaiting</b> your input, or <b>Planned</b>. The progress bar tracks how close you are to a complete draft.",
    placement: "right",
    pad: 4,
    radius: 0,
  },
  {
    target: "#ob-editor",
    title: "A real editor — with an agent inside",
    body: "Sections are drafted in editable text. Citations resolve to your project sources; you can rewrite any sentence by hand, or regenerate from your latest inputs.",
    placement: "left",
    pad: 0,
    radius: 0,
  },
  {
    target: "#ob-questions",
    title: "The agent asks; you answer",
    body: "Instead of guessing, Writer asks you the questions a reviewer would. Answer them and they get quoted directly into the right subsection — that's how a section moves from <i>Awaiting</i> to <i>Drafted</i>.",
    placement: "left",
    pad: 4,
    radius: 12,
  },
  {
    target: "#ob-tabs",
    title: "Sources & QA, one tab away",
    body: "Switch to <b>Sources</b> to see every paper cited in the current section (and suggest more), or <b>QA</b> for the agent's self-review — unresolved citations, claims without support, structural gaps.",
    placement: "bottom",
    pad: 6,
    radius: 10,
  },
  {
    target: "#ob-export",
    title: "Assemble & export",
    body: "When sections are <b>Drafted</b>, hit <b>Assemble</b> to stitch them into a single manuscript — abstract last, bibliography auto-generated. Export as <b>.tex + .bib</b> ready for Overleaf or arXiv.",
    placement: "bottom",
    pad: 6,
    radius: 12,
  },
  {
    kind: "welcome",
    eyebrow: "You're ready",
    title: "Pick a section and start drafting.",
    body: "Tip: start with <b>Methods</b> — it's the section the agent grounds best with your inputs. Open the chat workspace any time to add more sources.",
    primary: "Open Writer",
    secondary: "Back",
  },
];

/* ── Confluex logo SVG paths ───────────────────────────── */
const LOGO_PATHS = [
  "M 4,50 C 8,35 18,15 32,6",
  "M 9,52 C 13,36 24,16 39,7",
  "M 14,53 C 19,37 30,17 45,8",
  "M 19,54 C 25,38 36,18 51,9",
  "M 24,55 C 30,39 42,19 56,10",
  "M 29,55 C 36,40 47,21 58,14",
  "M 33,54 C 40,41 51,24 58,20",
  "M 37,53 C 43,42 53,27 57,26",
  "M 40,52 C 45,43 53,31 56,32",
];

/* ── Position calculation ──────────────────────────────── */
const CARD_WIDTH = 360;
const CARD_GAP = 18;

function calcCardPosition(
  rect: DOMRect,
  placement: "top" | "bottom" | "left" | "right",
  pad: number,
  cardHeight: number,
): { top: number; left: number; width: number } {
  // Use clientWidth/clientHeight to exclude scrollbar from available space
  const vw = document.documentElement.clientWidth;
  const vh = document.documentElement.clientHeight;
  // Cap card width so it never exceeds the viewport
  const W = Math.min(CARD_WIDTH, vw - 32);
  const H = cardHeight;
  const gap = CARD_GAP;

  let top: number;
  let left: number;

  if (placement === "right") {
    top = rect.top + rect.height / 2 - H / 2;
    left = rect.right + gap + pad;
  } else if (placement === "left") {
    top = rect.top + rect.height / 2 - H / 2;
    left = rect.left - gap - pad - W;
  } else if (placement === "top") {
    top = rect.top - gap - pad - H;
    left = rect.left + rect.width / 2 - W / 2;
  } else {
    top = rect.bottom + gap + pad;
    left = rect.left + rect.width / 2 - W / 2;
  }

  // clamp within safe viewport bounds
  top = Math.max(16, Math.min(top, vh - H - 16));
  left = Math.max(16, Math.min(left, vw - W - 16));

  return { top, left, width: W };
}

/* ── Main component ────────────────────────────────────── */

export default function OnboardingTour({ variant }: OnboardingTourProps) {
  const storageKey = variant === "chat" ? "onboarding-chat-done" : "onboarding-writer-done";
  const steps = variant === "chat" ? CHAT_STEPS : WRITER_STEPS;

  const [mounted, setMounted] = useState(false);
  const [active, setActive] = useState(false);
  const [showLauncher, setShowLauncher] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [spotlightRect, setSpotlightRect] = useState<DOMRect | null>(null);
  const [cardPos, setCardPos] = useState<{ top: number; left: number; width: number }>({ top: -9999, left: -9999, width: CARD_WIDTH });
  const [cardReady, setCardReady] = useState(false);

  const cardRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number | null>(null);

  /* ── Mount guard (SSR safety) ── */
  useEffect(() => {
    setMounted(true);
  }, []);

  /* ── Auto-start on first visit ── */
  useEffect(() => {
    if (!mounted) return;
    const done = localStorage.getItem(storageKey);
    if (!done) {
      setStepIndex(0);
      setActive(true);
    } else {
      setShowLauncher(true);
    }
  }, [mounted, storageKey]);

  /* ── Resolve spotlight target and position card ── */
  const resolveAndPosition = useCallback(
    (index: number) => {
      const step = steps[index];
      if (!step || step.kind === "welcome") {
        setSpotlightRect(null);
        setCardReady(false);
        return;
      }

      const target = document.querySelector<HTMLElement>(step.target);
      if (!target) {
        // skip this step
        setStepIndex((prev) => {
          const next = prev + 1;
          if (next < steps.length) return next;
          return prev;
        });
        return;
      }

      const rect = target.getBoundingClientRect();
      setCardReady(false);
      setSpotlightRect(rect);

      // Two-pass rAF: first frame lets the card render off-screen at -9999,
      // second frame reads its real offsetHeight before snapping into place.
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = requestAnimationFrame(() => {
          const cardH = cardRef.current?.offsetHeight ?? 240;
          const pos = calcCardPosition(rect, step.placement, step.pad, cardH);
          setCardPos(pos);
          setCardReady(true);
        });
      });
    },
    [steps],
  );

  useEffect(() => {
    if (!active) return;
    resolveAndPosition(stepIndex);
  }, [active, stepIndex, resolveAndPosition]);

  /* ── Resize listener ── */
  useEffect(() => {
    if (!active) return;
    const handleResize = () => resolveAndPosition(stepIndex);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [active, stepIndex, resolveAndPosition]);

  /* ── Cleanup rAF on unmount ── */
  useEffect(() => {
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  /* ── Handlers ── */
  const dismiss = useCallback(() => {
    setActive(false);
    setShowLauncher(true);
    setSpotlightRect(null);
    localStorage.setItem(storageKey, "1");
  }, [storageKey]);

  const restart = useCallback(() => {
    setShowLauncher(false);
    setStepIndex(0);
    setActive(true);
  }, []);

  const goNext = useCallback(() => {
    const next = stepIndex + 1;
    if (next >= steps.length) {
      dismiss();
    } else {
      setStepIndex(next);
    }
  }, [stepIndex, steps.length, dismiss]);

  const goPrev = useCallback(() => {
    const prev = stepIndex - 1;
    if (prev >= 0) setStepIndex(prev);
  }, [stepIndex]);

  /* ── Don't render until mounted on client ── */
  if (!mounted) return null;

  const step = steps[stepIndex];
  // Count of inner steps (excluding welcome at 0 and finale at last)
  const innerTotal = steps.length - 2;
  const isWelcome = step.kind === "welcome";
  const isFinale = stepIndex === steps.length - 1;

  const tourOverlay = (
    <>
      {/* Global CSS for ob-kbd and ob-pulse animation */}
      <style>{`
        .ob-kbd {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-width: 22px;
          height: 22px;
          padding: 0 6px;
          border-radius: 6px;
          background: #efeeec;
          color: #444841;
          border: 1px solid rgba(116,120,112,.25);
          border-bottom-width: 2px;
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
          font-size: 11px;
        }
        @keyframes ob-pulse {
          0%, 100% { transform: scale(1); opacity: 0.85; }
          50% { transform: scale(1.03); opacity: 0.25; }
        }
        .ob-spotlight-pulse::after {
          content: "";
          position: absolute;
          inset: -6px;
          border-radius: inherit;
          box-shadow: 0 0 0 2px rgba(220,236,205,0.55);
          animation: ob-pulse 2.4s ease-in-out infinite;
        }
      `}</style>

      {active && isWelcome && (
        <WelcomeModal
          step={step as WelcomeStep}
          stepIndex={stepIndex}
          totalInner={innerTotal}
          isFinale={isFinale}
          onPrimary={isFinale ? dismiss : goNext}
          onSecondary={isFinale ? goPrev : dismiss}
        />
      )}

      {active && !isWelcome && spotlightRect && (
        <SpotlightOverlay
          step={step as SpotlightStep}
          stepIndex={stepIndex}
          totalInner={innerTotal}
          spotlightRect={spotlightRect}
          cardPos={cardPos}
          cardReady={cardReady}
          cardRef={cardRef}
          onNext={goNext}
          onPrev={goPrev}
          onSkip={dismiss}
          isLast={stepIndex === steps.length - 2}
        />
      )}

      {showLauncher && (
        <button
          type="button"
          onClick={restart}
          className="fixed right-6 bottom-6 z-[55] inline-flex items-center rounded-full bg-[#1d2d18] p-2.5 text-white shadow-lg transition-colors hover:bg-[#32432c]"
          aria-label="Restart tour"
        >
          <span className="material-symbols-outlined" style={{ fontSize: "16px", fontVariationSettings: "'FILL' 0,'wght' 300,'GRAD' 0,'opsz' 20", marginLeft: "4px" }}>
            tips_and_updates
          </span>
        </button>
      )}
    </>
  );

  return createPortal(tourOverlay, document.body);
}

/* ── Step dots ─────────────────────────────────────────── */

function StepDots({ total, current }: { total: number; current: number }) {
  return (
    <div className="flex items-center gap-[5px]">
      {Array.from({ length: total }, (_, i) => {
        const k = i + 1;
        const isActive = k === current;
        const isDone = k < current;
        return (
          <span
            key={i}
            style={{
              display: "block",
              height: "3px",
              borderRadius: "999px",
              transition: "background 0.2s, width 0.25s",
              width: isActive ? "22px" : "16px",
              background: isActive ? "#32432c" : isDone ? "#9cb092" : "#c4c8be",
            }}
          />
        );
      })}
    </div>
  );
}

/* ── Confluex logo ─────────────────────────────────────── */

function ConfluexLogo({ size = 44 }: { size?: number }) {
  return (
    <svg viewBox="0 0 62 60" width={size} height={size} aria-hidden="true">
      {LOGO_PATHS.map((d, i) => (
        <path key={i} d={d} stroke="#32432c" strokeWidth="1.6" strokeLinecap="round" fill="none" />
      ))}
    </svg>
  );
}

/* ── Welcome / Finale modal ────────────────────────────── */

interface WelcomeModalProps {
  step: WelcomeStep;
  stepIndex: number;
  totalInner: number;
  isFinale: boolean;
  onPrimary: () => void;
  onSecondary: () => void;
}

function WelcomeModal({ step, stepIndex, totalInner, isFinale, onPrimary, onSecondary }: WelcomeModalProps) {
  const isIntro = stepIndex === 0;

  return (
    <div
      className="fixed inset-0 z-[62] flex items-center justify-center"
      style={{ background: "rgba(15,18,15,0.55)" }}
      role="dialog"
      aria-modal="true"
      aria-label={step.title}
    >
      <div
        className="overflow-hidden rounded-[20px] bg-white"
        style={{
          width: "min(520px, calc(100vw - 32px))",
          boxShadow: "0 30px 60px -20px rgba(15,18,15,0.55)",
        }}
      >
        {/* Glyph strip header */}
        <div
          className="flex items-start gap-4 border-b px-8 pb-6 pt-7"
          style={{
            borderColor: "rgba(116,120,112,.18)",
            background:
              "radial-gradient(120% 200% at 100% 0%, rgba(156,176,146,0.20), transparent 55%), linear-gradient(180deg, #f4f3f1 0%, #efeeec 100%)",
          }}
        >
          <div className="shrink-0">
            <ConfluexLogo size={44} />
          </div>
          <div className="min-w-0">
            <p
              style={{
                fontSize: "10px",
                fontWeight: 700,
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                color: "#8C8375",
              }}
            >
              {step.eyebrow}
            </p>
            <h2
              style={{
                fontFamily: "'Noto Serif', serif",
                fontSize: "22px",
                lineHeight: 1.2,
                fontWeight: 500,
                color: "#1a1c1b",
                marginTop: "4px",
                textWrap: "balance",
              } as React.CSSProperties}
            >
              {step.title}
            </h2>
          </div>
        </div>

        {/* Body */}
        <div className="px-8 py-6">
          <p style={{ fontSize: "13px", lineHeight: 1.55, color: "#444841" }}>{step.body}</p>

          {/* Feature cards (intro only) */}
          {isIntro && step.featureCards && step.featureCards.length > 0 && (
            <div className="mt-5 grid grid-cols-3 gap-3">
              {step.featureCards.map((card, i) => (
                <div
                  key={i}
                  className="rounded-xl border border-outline/20 bg-surface-container-low px-3 py-3"
                >
                  <span
                    className="material-symbols-outlined text-primary"
                    style={{ fontSize: "20px", fontVariationSettings: "'FILL' 0,'wght' 300,'GRAD' 0,'opsz' 20" }}
                  >
                    {card.icon}
                  </span>
                  <p className="mt-1 text-[11px] font-semibold text-on-surface">{card.title}</p>
                  <p className="mt-0.5 text-[11px] leading-snug text-on-surface-variant">{card.body}</p>
                </div>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="mt-6 flex items-center justify-between">
            <button
              type="button"
              onClick={onSecondary}
              className="inline-flex h-9 items-center justify-center gap-1.5 rounded-full px-4 text-xs font-semibold text-on-surface-variant transition-all hover:bg-[rgba(50,67,44,0.08)] hover:text-on-surface"
            >
              {step.secondary}
            </button>
            <div className="flex items-center gap-3">
              <StepDots total={totalInner} current={isFinale ? totalInner + 1 : 0} />
              <button
                type="button"
                onClick={onPrimary}
                className="inline-flex h-9 items-center justify-center gap-1.5 rounded-full bg-[#1d2d18] px-4 text-xs font-semibold text-white transition-colors hover:bg-[#32432c]"
              >
                {step.primary}
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: "16px", fontVariationSettings: "'FILL' 0,'wght' 300,'GRAD' 0,'opsz' 20" }}
                >
                  arrow_forward
                </span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Spotlight overlay ─────────────────────────────────── */

interface SpotlightOverlayProps {
  step: SpotlightStep;
  stepIndex: number;
  totalInner: number;
  spotlightRect: DOMRect;
  cardPos: { top: number; left: number; width: number };
  cardReady: boolean;
  cardRef: React.RefObject<HTMLDivElement>;
  onNext: () => void;
  onPrev: () => void;
  onSkip: () => void;
  isLast: boolean;
}

function SpotlightOverlay({
  step,
  stepIndex,
  totalInner,
  spotlightRect,
  cardPos,
  cardReady,
  cardRef,
  onNext,
  onPrev,
  onSkip,
  isLast,
}: SpotlightOverlayProps) {
  const pad = step.pad;
  const radius = step.radius;

  const spotTop = spotlightRect.top - pad;
  const spotLeft = spotlightRect.left - pad;
  const spotWidth = spotlightRect.width + pad * 2;
  const spotHeight = spotlightRect.height + pad * 2;

  return (
    <>
      {/* Clickable backdrop (dismiss on click) */}
      <div
        className="fixed inset-0 z-[60]"
        style={{ pointerEvents: "auto" }}
        onClick={onSkip}
        aria-hidden="true"
      />

      {/* Spotlight cutout using box-shadow technique */}
      <div
        className="ob-spotlight-pulse fixed z-[61] pointer-events-none"
        style={{
          top: `${spotTop}px`,
          left: `${spotLeft}px`,
          width: `${spotWidth}px`,
          height: `${spotHeight}px`,
          borderRadius: `${radius}px`,
          boxShadow:
            "0 0 0 4px rgba(50,67,44,0.30), 0 0 0 9999px rgba(15,18,15,0.55)",
          transition:
            "top 380ms cubic-bezier(.4,0,.2,1), left 380ms cubic-bezier(.4,0,.2,1), width 380ms cubic-bezier(.4,0,.2,1), height 380ms cubic-bezier(.4,0,.2,1), border-radius 280ms ease",
        }}
      />

      {/* Tooltip card */}
      <div
        ref={cardRef}
        className="fixed z-[62] overflow-hidden rounded-2xl bg-white"
        style={{
          top: `${cardPos.top}px`,
          left: `${cardPos.left}px`,
          width: `${cardPos.width}px`,
          maxWidth: "calc(100vw - 32px)",
          boxShadow:
            "0 18px 50px -10px rgba(15,18,15,0.45), 0 4px 14px -4px rgba(15,18,15,0.25)",
          transition: cardReady
            ? "top 380ms cubic-bezier(.4,0,.2,1), left 380ms cubic-bezier(.4,0,.2,1), opacity 150ms ease"
            : "none",
          opacity: cardReady ? 1 : 0,
          pointerEvents: "auto",
        }}
        role="tooltip"
        aria-live="polite"
      >
        {/* Card body */}
        <div className="px-5 pb-3 pt-4">
          <p
            style={{
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: "#8C8375",
            }}
          >
            Step {stepIndex} of {totalInner}
          </p>
          <h3
            style={{
              fontFamily: "'Noto Serif', serif",
              fontSize: "17px",
              lineHeight: 1.25,
              fontWeight: 500,
              color: "#1a1c1b",
              marginTop: "3px",
            }}
          >
            {step.title}
          </h3>
          <p
            className="mt-2"
            style={{ fontSize: "13px", lineHeight: 1.5, color: "#444841" }}
            dangerouslySetInnerHTML={{ __html: step.body }}
          />
        </div>

        {/* Card footer */}
        <div
          className="flex items-center justify-between border-t px-5 py-3"
          style={{
            borderColor: "rgba(116,120,112,.15)",
            background: "rgba(244,243,241,0.6)",
          }}
        >
          <StepDots total={totalInner} current={stepIndex} />
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={onSkip}
              className="inline-flex h-8 items-center justify-center rounded-full px-3 text-xs font-semibold text-on-surface-variant transition-all hover:bg-[rgba(50,67,44,0.08)] hover:text-on-surface"
            >
              Skip
            </button>
            {stepIndex > 1 && (
              <button
                type="button"
                onClick={onPrev}
                className="inline-flex h-8 items-center justify-center rounded-full border border-outline/40 bg-[#faf9f7] px-3 text-xs font-semibold text-on-surface transition-colors hover:bg-[#efeeec]"
              >
                Back
              </button>
            )}
            <button
              type="button"
              onClick={onNext}
              className="inline-flex h-8 items-center justify-center gap-1 rounded-full bg-[#1d2d18] px-3 text-xs font-semibold text-white transition-colors hover:bg-[#32432c]"
            >
              {isLast ? "Finish" : "Next"}
              <span
                className="material-symbols-outlined"
                style={{ fontSize: "15px", fontVariationSettings: "'FILL' 0,'wght' 300,'GRAD' 0,'opsz' 20" }}
              >
                arrow_forward
              </span>
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
