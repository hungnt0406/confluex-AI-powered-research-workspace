"use client";

import { useState } from "react";
import Link from "next/link";

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

type CtaStyle = "primary" | "outline";

interface PlanFeature {
  t: string;
  strong?: boolean;
}

interface Plan {
  id: string;
  name: string;
  tagline: string;
  bestFor: string;
  monthly: number;
  annual: number;
  cta: string;
  ctaStyle: CtaStyle;
  features: PlanFeature[];
  limit: string;
  badge?: string;
  perSeat?: boolean;
}

const PLANS: Plan[] = [
  {
    id: "free",
    name: "Free",
    tagline: "For curious afternoons.",
    bestFor: "Trial users · students testing the waters",
    monthly: 0,
    annual: 0,
    cta: "Start with Free",
    ctaStyle: "outline",
    features: [
      { t: "1–2 active projects", strong: true },
      { t: "Limited paper search across the index" },
      { t: "Up to 5 PDF uploads", strong: true },
      { t: "Basic chat with one paper at a time" },
      { t: "1 short research report / month" },
      { t: "Notes & highlights, kept forever" },
    ],
    limit: "No exports — read & explore only.",
  },
  {
    id: "student",
    name: "Student",
    tagline: "For coursework & first papers.",
    bestFor: "Students, casual researchers",
    monthly: 8,
    annual: 6,
    cta: "Get Student access",
    ctaStyle: "outline",
    features: [
      { t: "5–10 projects, organized by class" },
      { t: "50 PDF uploads", strong: true },
      { t: "10 Deep Search reports / month", strong: true },
      { t: "Basic Writer outputs (essays, summaries)" },
      { t: "BibTeX & Markdown export" },
      { t: "Citation drag-and-drop into your editor" },
    ],
    limit: "Verified .edu email or student ID required.",
  },
  {
    id: "researcher",
    name: "Researcher Pro",
    tagline: "For your serious thread of work.",
    bestFor: "Solo researchers · grad students · postdocs",
    monthly: 24,
    annual: 19,
    cta: "Begin Researcher Pro",
    ctaStyle: "primary",
    badge: "Most chosen",
    features: [
      { t: "Unlimited projects" },
      { t: "200 PDF uploads", strong: true },
      { t: "40 Deep Search reports / month", strong: true },
      { t: "Full Writer workspace with versions" },
      { t: "APA, MLA, Chicago, Vancouver citations" },
      { t: "Saved outputs & reading-trail history" },
      { t: "Source previews inline with claims" },
    ],
    limit: "Bring-your-own-model supported.",
  },
  {
    id: "lab",
    name: "Lab / Team",
    tagline: "For groups thinking together.",
    bestFor: "Research groups & small teams",
    monthly: 22,
    annual: 18,
    cta: "Set up the lab",
    ctaStyle: "outline",
    perSeat: true,
    features: [
      { t: "Everything in Researcher Pro, per seat" },
      { t: "Shared projects & libraries", strong: true },
      { t: "Pooled Deep Search credits", strong: true },
      { t: "Admin usage dashboard" },
      { t: "Real-time collaboration on writing" },
      { t: "Priority queue for long reports" },
      { t: "Single team invoice & billing" },
    ],
    limit: "Min. 3 seats. Annual or monthly.",
  },
];

interface CompareRow {
  f: string;
  v: (string | boolean)[];
}

interface CompareGroup {
  group: string;
  rows: CompareRow[];
}

const COMPARE: CompareGroup[] = [
  {
    group: "Library",
    rows: [
      { f: "Active projects", v: ["1–2", "5–10", "Unlimited", "Unlimited"] },
      { f: "PDF uploads", v: ["5", "50", "200", "Pooled"] },
      { f: "Paper search across index", v: ["Limited", "Full", "Full + filters", "Full + filters"] },
      { f: "Source previews & citation trail", v: [false, true, true, true] },
    ],
  },
  {
    group: "Intelligence",
    rows: [
      { f: "Chat with papers", v: ["Single", "Multi-paper", "Multi-paper", "Multi-paper"] },
      { f: "Deep Search reports / month", v: ["1 short", "10", "40", "Pooled"] },
      { f: "Writer workspace", v: [false, "Basic", "Full", "Full"] },
      { f: "Bring your own model", v: [false, false, true, true] },
    ],
  },
  {
    group: "Output",
    rows: [
      { f: "BibTeX / Markdown export", v: [false, true, true, true] },
      { f: "Citation styles (APA, MLA, …)", v: [false, "Basic", "All", "All"] },
      { f: "Saved outputs & versions", v: [false, false, true, true] },
    ],
  },
  {
    group: "Team & control",
    rows: [
      { f: "Shared projects & libraries", v: [false, false, false, true] },
      { f: "Admin dashboard & usage", v: [false, false, false, true] },
      { f: "Priority queue for long reports", v: [false, false, false, true] },
      { f: "Single team invoice & billing", v: [false, false, false, true] },
    ],
  },
];

const ADDONS = [
  {
    icon: "bolt",
    name: "Deep Search top-up",
    desc: "10 extra reports, never expire. Stack as many as you need.",
    price: "$6",
    priceNote: "per pack",
    dark: false,
  },
  {
    icon: "upload_file",
    name: "PDF storage bump",
    desc: "Add 100 more upload slots to any plan, permanently.",
    price: "$4",
    priceNote: "per month",
    dark: false,
  },
  {
    icon: "hub",
    name: "Enterprise & Institution",
    desc: "Custom seats, SSO, regional storage, compliance SLA. Let's talk.",
    price: "Custom",
    priceNote: "contact us",
    dark: true,
  },
];

interface FaqItem {
  q: string;
  a: string;
}

const FAQ: FaqItem[] = [
  {
    q: "Can I switch plans mid-month?",
    a: "Yes. Upgrades prorate immediately and you keep the new limits the same day. Downgrades take effect at the next renewal so you don't lose access mid-paper.",
  },
  {
    q: "What counts as a Deep Search report?",
    a: "One agentic, multi-hop research run that ends with a synthesized memo and a citation list. Quick chats, single-paper questions, and re-runs of the same query within 24 hours don't burn a credit.",
  },
  {
    q: "Do my uploads stay private?",
    a: "Always. Documents you upload are scoped to your projects, encrypted at rest, and never used to train shared models. Institution plans add custom retention and regional storage.",
  },
  {
    q: "Is there a real student discount?",
    a: "Yes — verified through SheerID with a current .edu email or student ID. The Student plan stays at its discounted rate as long as you stay enrolled, re-verified once a year.",
  },
  {
    q: "What happens when I hit a limit?",
    a: "You'll keep read access to everything you've already added, and we'll prompt you to upgrade or buy a top-up pack. We never silently delete your work.",
  },
  {
    q: "How does Lab pooling work?",
    a: "All Deep Search credits and PDF capacity become shared resources for the team. The admin dashboard shows who's using what so power users don't quietly drain the pool.",
  },
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Logo() {
  return (
    <div className="flex items-center gap-2">
      <svg
        viewBox="0 0 62 60"
        width={28}
        height={28}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
        style={{ flexShrink: 0 }}
      >
        {[
          "M 4,50 C 8,35 18,15 32,6",
          "M 9,52 C 13,36 24,16 39,7",
          "M 14,53 C 19,37 30,17 45,8",
          "M 19,54 C 25,38 36,18 51,9",
          "M 24,55 C 30,39 42,19 56,10",
          "M 29,55 C 36,40 47,21 58,14",
          "M 33,54 C 40,41 51,24 58,20",
          "M 37,53 C 43,42 53,27 57,26",
          "M 40,52 C 45,43 53,31 56,32",
        ].map((d, i) => (
          <path key={i} d={d} stroke="#32432c" strokeWidth="1.6" strokeLinecap="round" fill="none" />
        ))}
      </svg>
      <span
        style={{
          fontFamily: "'Inter', sans-serif",
          fontWeight: 600,
          color: "#1d2d18",
          letterSpacing: "-0.01em",
          fontSize: "1.0625rem",
          lineHeight: 1,
        }}
      >
        confluex
      </span>
    </div>
  );
}

interface BillingToggleProps {
  billing: "monthly" | "annual";
  onChange: (v: "monthly" | "annual") => void;
}

function BillingToggle({ billing, onChange }: BillingToggleProps) {
  return (
    <div
      className="inline-flex items-center gap-1 rounded-full p-1"
      style={{ background: "#efeeec" }}
      role="radiogroup"
      aria-label="Billing period"
    >
      <button
        role="radio"
        aria-checked={billing === "monthly"}
        onClick={() => onChange("monthly")}
        className="rounded-full px-5 py-1.5 text-sm font-medium transition-all duration-200"
        style={
          billing === "monthly"
            ? { background: "#1d2d18", color: "#fff" }
            : { background: "transparent", color: "#444841" }
        }
      >
        Monthly
      </button>
      <button
        role="radio"
        aria-checked={billing === "annual"}
        onClick={() => onChange("annual")}
        className="flex items-center gap-1.5 rounded-full px-5 py-1.5 text-sm font-medium transition-all duration-200"
        style={
          billing === "annual"
            ? { background: "#1d2d18", color: "#fff" }
            : { background: "transparent", color: "#444841" }
        }
      >
        Annual
        <span
          className="rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none"
          style={
            billing === "annual"
              ? { background: "#9cb092", color: "#1d2d18" }
              : { background: "#dee5d5", color: "#596154" }
          }
        >
          −20%
        </span>
      </button>
    </div>
  );
}

interface PlanCardProps {
  plan: Plan;
  billing: "monthly" | "annual";
}

function PlanCard({ plan, billing }: PlanCardProps) {
  const featured = plan.id === "researcher";
  const price = billing === "annual" ? plan.annual : plan.monthly;

  return (
    <div
      className="relative flex flex-col rounded-2xl p-6 transition-transform duration-200 hover:-translate-y-[3px]"
      style={{
        background: featured ? "#1d2d18" : "#ffffff",
        border: featured ? "none" : "1px solid rgba(196,200,190,0.6)",
      }}
    >
      {/* Badge */}
      {plan.badge && (
        <span
          className="absolute -top-3 left-6 rounded-full px-3 py-1 text-xs font-semibold"
          style={{ background: "#dee5d5", color: "#1d2d18" }}
        >
          {plan.badge}
        </span>
      )}

      {/* Plan name + tagline */}
      <div className="mb-5">
        <p
          className="text-xs font-semibold uppercase tracking-widest mb-1"
          style={{ color: featured ? "#9cb092" : "#596154" }}
        >
          {plan.name}
        </p>
        <p
          className="font-headline text-base italic leading-snug"
          style={{ color: featured ? "rgba(255,255,255,0.75)" : "#444841" }}
        >
          {plan.tagline}
        </p>
      </div>

      {/* Price */}
      <div className="mb-1 flex items-end gap-1">
        {price === 0 ? (
          <span
            className="font-headline text-[44px] leading-none font-semibold"
            style={{ color: featured ? "#ffffff" : "#1d2d18" }}
          >
            Free
          </span>
        ) : (
          <>
            <span
              className="font-headline text-[44px] leading-none font-semibold"
              style={{ color: featured ? "#ffffff" : "#1d2d18" }}
            >
              ${price}
            </span>
            <span
              className="mb-2 text-sm"
              style={{ color: featured ? "rgba(255,255,255,0.5)" : "#747870" }}
            >
              / mo{plan.perSeat ? " / seat" : ""}
            </span>
          </>
        )}
      </div>

      {/* Annual note */}
      {billing === "annual" && price > 0 && (
        <p className="mb-4 text-xs" style={{ color: featured ? "#9cb092" : "#596154" }}>
          Billed ${plan.annual * 12} / year
        </p>
      )}
      {(billing === "monthly" || price === 0) && <div className="mb-4" />}

      {/* Best for */}
      <p
        className="mb-5 text-xs leading-relaxed"
        style={{ color: featured ? "rgba(255,255,255,0.5)" : "#8C8375" }}
      >
        {plan.bestFor}
      </p>

      {/* CTA */}
      <Link
        href="/login"
        className="mb-6 flex items-center justify-center rounded-full py-2.5 text-sm font-medium transition-all duration-200 hover:opacity-90 active:scale-[0.98]"
        style={
          featured
            ? { background: "#ffffff", color: "#1d2d18" }
            : plan.ctaStyle === "primary"
            ? { background: "#1d2d18", color: "#ffffff" }
            : {
                background: "transparent",
                color: featured ? "#ffffff" : "#1d2d18",
                border: `1px solid ${featured ? "rgba(255,255,255,0.3)" : "rgba(29,45,24,0.35)"}`,
              }
        }
      >
        {plan.cta}
      </Link>

      {/* Divider */}
      <div
        className="mb-5 h-px w-full"
        style={{ background: featured ? "rgba(255,255,255,0.1)" : "rgba(196,200,190,0.5)" }}
      />

      {/* Features */}
      <ul className="flex flex-col gap-2.5 flex-1">
        {plan.features.map((feat, i) => (
          <li key={i} className="flex items-start gap-2">
            <span
              className="material-symbols-outlined mt-0.5 shrink-0"
              style={{
                fontSize: "16px",
                fontVariationSettings: "'FILL' 1, 'wght' 500, 'GRAD' 0, 'opsz' 20",
                color: feat.strong
                  ? featured
                    ? "#9cb092"
                    : "#1d2d18"
                  : featured
                  ? "rgba(255,255,255,0.4)"
                  : "#747870",
              }}
            >
              check
            </span>
            <span
              className={`text-xs leading-relaxed ${feat.strong ? "font-medium" : ""}`}
              style={{
                color: feat.strong
                  ? featured
                    ? "#ffffff"
                    : "#1a1c1b"
                  : featured
                  ? "rgba(255,255,255,0.6)"
                  : "#444841",
              }}
            >
              {feat.t}
            </span>
          </li>
        ))}
      </ul>

      {/* Limit note */}
      <p
        className="mt-5 text-[11px] leading-relaxed"
        style={{ color: featured ? "rgba(255,255,255,0.35)" : "#8C8375" }}
      >
        {plan.limit}
      </p>
    </div>
  );
}

function CompareCell({ value }: { value: string | boolean }) {
  if (value === true) {
    return (
      <span
        className="material-symbols-outlined mt-0.5 shrink-0"
        style={{
          fontSize: "16px",
          fontVariationSettings: "'FILL' 1, 'wght' 500, 'GRAD' 0, 'opsz' 20",
          color: "#1d2d18",
        }}
      >
        check
      </span>
    );
  }
  if (value === false) {
    return (
      <span style={{ color: "#c4c8be" }}>
        —
      </span>
    );
  }
  return <span className="text-sm text-on-surface">{value}</span>;
}

interface FaqItemComponentProps {
  item: FaqItem;
  index: number;
  openIndex: number | null;
  onToggle: (i: number) => void;
}

function FaqItemComponent({ item, index, openIndex, onToggle }: FaqItemComponentProps) {
  const isOpen = openIndex === index;

  return (
    <div className="border-b border-outline-variant/50">
      <button
        className="flex w-full items-center justify-between gap-4 py-5 text-left"
        onClick={() => onToggle(index)}
        aria-expanded={isOpen}
      >
        <span className="text-sm font-medium text-on-surface">{item.q}</span>
        <span
          className="material-symbols-outlined shrink-0 text-on-surface-variant transition-transform duration-200"
          style={{
            fontSize: "20px",
            transform: isOpen ? "rotate(180deg)" : "rotate(0deg)",
          }}
        >
          expand_more
        </span>
      </button>
      <div
        className="overflow-hidden transition-all duration-200"
        style={{ maxHeight: isOpen ? "240px" : "0px" }}
      >
        <p className="pb-5 pr-8 text-sm leading-relaxed text-on-surface-variant">{item.a}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PricingPage() {
  const [billing, setBilling] = useState<"monthly" | "annual">("monthly");
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  const handleFaqToggle = (i: number) => {
    setOpenFaq((prev) => (prev === i ? null : i));
  };

  return (
    <div className="h-screen overflow-y-auto bg-background">
      {/* ------------------------------------------------------------------ */}
      {/* Header */}
      {/* ------------------------------------------------------------------ */}
      <header
        className="sticky top-0 z-50 flex items-center justify-between px-6 md:px-10"
        style={{
          height: "64px",
          borderBottom: "1px solid rgba(116,120,112,0.15)",
          background: "rgba(250,249,247,0.85)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
        }}
      >
        <Link href="/chat" className="no-underline">
          <Logo />
        </Link>

        <div className="flex items-center gap-2">
          <Link
            href="/chat"
            className="flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium text-on-surface-variant transition-colors hover:bg-primary/5 no-underline"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
              arrow_back
            </span>
            Back to workspace
          </Link>
          <Link
            href="/login"
            className="rounded-full px-4 py-2 text-sm font-medium transition-colors hover:bg-primary/5 text-on-surface no-underline"
          >
            Sign in
          </Link>
          <Link
            href="/login"
            className="rounded-full px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 no-underline"
            style={{ background: "#1d2d18" }}
          >
            Get started
          </Link>
        </div>
      </header>

      {/* ------------------------------------------------------------------ */}
      {/* Hero */}
      {/* ------------------------------------------------------------------ */}
      <section className="mx-auto max-w-4xl px-6 pb-12 pt-20 text-center md:pt-24">
        <h1 className="font-headline text-[clamp(3rem,8vw,5rem)] font-semibold leading-[1.05] tracking-tight text-on-surface">
          Pricing for every{" "}
          <em className="font-headline italic">stage</em>{" "}
          of research.
        </h1>
        <p
          className="mx-auto mt-6 max-w-2xl text-[15px] leading-relaxed"
          style={{ color: "#444841" }}
        >
          From a curious afternoon with one paper to an entire lab synthesizing a field —
          Confluex grows with the depth of your inquiry. Cancel any time, keep your notes forever.
        </p>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Billing toggle */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex justify-center pb-10">
        <BillingToggle billing={billing} onChange={setBilling} />
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Plan cards */}
      {/* ------------------------------------------------------------------ */}
      <section className="mx-auto max-w-6xl px-6 pb-20">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PLANS.map((plan) => (
            <PlanCard key={plan.id} plan={plan} billing={billing} />
          ))}
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Comparison table */}
      {/* ------------------------------------------------------------------ */}
      <section className="mx-auto max-w-6xl px-6 pb-24">
        <h2
          className="font-headline mb-2 text-2xl font-semibold text-on-surface"
        >
          Compare plans
        </h2>
        <p className="mb-8 text-sm text-on-surface-variant">
          Every feature, laid flat.
        </p>

        <div
          className="overflow-hidden rounded-2xl"
          style={{ border: "1px solid rgba(196,200,190,0.5)" }}
        >
          {/* Column headers */}
          <div
            className="grid"
            style={{
              gridTemplateColumns: "1fr repeat(4, minmax(100px, 1fr))",
              background: "#f4f3f1",
              borderBottom: "1px solid rgba(196,200,190,0.5)",
            }}
          >
            <div className="px-5 py-4" />
            {PLANS.map((p) => (
              <div key={p.id} className="px-4 py-4 text-center">
                <span
                  className="text-xs font-semibold uppercase tracking-wider"
                  style={{ color: "#1d2d18" }}
                >
                  {p.name}
                </span>
              </div>
            ))}
          </div>

          {/* Groups */}
          {COMPARE.map((group, gi) => (
            <div key={gi}>
              {/* Group header */}
              <div
                className="grid"
                style={{
                  gridTemplateColumns: "1fr repeat(4, minmax(100px, 1fr))",
                  background: "#f4f3f1",
                  borderTop: gi > 0 ? "1px solid rgba(196,200,190,0.5)" : undefined,
                }}
              >
                <div className="col-span-5 px-5 py-2.5">
                  <span
                    className="text-[11px] font-bold uppercase tracking-[0.12em]"
                    style={{ color: "#1d2d18" }}
                  >
                    {group.group}
                  </span>
                </div>
              </div>

              {/* Rows */}
              {group.rows.map((row, ri) => (
                <div
                  key={ri}
                  className="grid"
                  style={{
                    gridTemplateColumns: "1fr repeat(4, minmax(100px, 1fr))",
                    background: ri % 2 === 0 ? "#ffffff" : "#faf9f7",
                    borderTop: "1px solid rgba(196,200,190,0.25)",
                  }}
                >
                  <div className="flex items-center px-5 py-3.5">
                    <span className="text-sm text-on-surface">{row.f}</span>
                  </div>
                  {row.v.map((val, ci) => (
                    <div key={ci} className="flex items-center justify-center px-4 py-3.5">
                      <CompareCell value={val} />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Add-ons */}
      {/* ------------------------------------------------------------------ */}
      <section className="mx-auto max-w-6xl px-6 pb-24">
        <h2 className="font-headline mb-2 text-2xl font-semibold text-on-surface">Add-ons</h2>
        <p className="mb-8 text-sm text-on-surface-variant">
          Bolt on what you need, nothing more.
        </p>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {ADDONS.map((addon, i) => (
            <div
              key={i}
              className="flex flex-col rounded-2xl p-6 transition-transform duration-200 hover:-translate-y-[3px]"
              style={{
                background: addon.dark ? "#1d2d18" : "#ffffff",
                border: addon.dark ? "none" : "1px solid rgba(196,200,190,0.6)",
              }}
            >
              <span
                className="material-symbols-outlined mb-4"
                style={{
                  fontSize: "24px",
                  fontVariationSettings: "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 24",
                  color: addon.dark ? "#9cb092" : "#1d2d18",
                }}
              >
                {addon.icon}
              </span>
              <p
                className="mb-1 text-sm font-semibold"
                style={{ color: addon.dark ? "#ffffff" : "#1a1c1b" }}
              >
                {addon.name}
              </p>
              <p
                className="mb-4 flex-1 text-xs leading-relaxed"
                style={{ color: addon.dark ? "rgba(255,255,255,0.55)" : "#444841" }}
              >
                {addon.desc}
              </p>
              <div className="flex items-baseline gap-1.5">
                <span
                  className="font-headline text-2xl font-semibold"
                  style={{ color: addon.dark ? "#ffffff" : "#1d2d18" }}
                >
                  {addon.price}
                </span>
                <span
                  className="text-xs"
                  style={{ color: addon.dark ? "rgba(255,255,255,0.4)" : "#747870" }}
                >
                  {addon.priceNote}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* FAQ */}
      {/* ------------------------------------------------------------------ */}
      <section className="mx-auto max-w-2xl px-6 pb-28">
        <h2 className="font-headline mb-8 text-2xl font-semibold text-on-surface text-center">
          Frequently asked
        </h2>

        <div>
          {FAQ.map((item, i) => (
            <FaqItemComponent
              key={i}
              item={item}
              index={i}
              openIndex={openFaq}
              onToggle={handleFaqToggle}
            />
          ))}
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Footer CTA */}
      {/* ------------------------------------------------------------------ */}
      <section className="mx-auto max-w-6xl px-6 pb-16">
        <div
          className="relative overflow-hidden rounded-3xl px-10 py-14 md:px-14 md:py-16"
          style={{ background: "#1d2d18" }}
        >
          <div className="relative z-10 grid items-end gap-10 md:grid-cols-[1fr_auto]">
            <div>
              <p
                className="mb-4 text-xs font-semibold uppercase tracking-[0.22em]"
                style={{ color: "#9cb092" }}
              >
                Start where you are
              </p>
              <h2 className="font-headline text-[clamp(2.4rem,5vw,3.5rem)] font-semibold leading-[1.05] tracking-tight text-white">
                Open a project. Drop in a paper.{" "}
                <em className="font-headline italic">See what happens.</em>
              </h2>
              <p
                className="mt-5 max-w-lg text-[15px] leading-relaxed"
                style={{ color: "rgba(255,255,255,0.65)" }}
              >
                The free plan has no clock and no card. You&apos;ll know within an hour of
                reading whether Confluex belongs in your workflow.
              </p>
            </div>
            <div className="flex flex-col gap-3">
              <Link
                href="/login"
                className="rounded-full px-8 py-3.5 text-sm font-semibold text-on-surface transition-opacity hover:opacity-90 text-center no-underline"
                style={{ background: "#ffffff" }}
              >
                Start with Free
              </Link>
              <Link
                href="/login"
                className="rounded-full border px-8 py-3.5 text-sm font-medium text-white transition-opacity hover:opacity-75 text-center no-underline"
                style={{ borderColor: "rgba(255,255,255,0.35)" }}
              >
                Talk to our team
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Footer */}
      {/* ------------------------------------------------------------------ */}
      <footer
        className="mx-auto max-w-6xl px-6 pb-10 pt-6"
        style={{ borderTop: "1px solid rgba(196,200,190,0.4)" }}
      >
        <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
          <Logo />
          <nav className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2">
            {["Privacy", "Terms", "Status", "Contact"].map((label) => (
              <Link
                key={label}
                href="#"
                className="text-xs text-on-surface-variant transition-colors hover:text-on-surface no-underline"
              >
                {label}
              </Link>
            ))}
          </nav>
          <p className="text-xs" style={{ color: "#8C8375" }}>
            &copy; {new Date().getFullYear()} Confluex
          </p>
        </div>
      </footer>
    </div>
  );
}
