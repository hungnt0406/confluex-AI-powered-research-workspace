/* Confluex pricing — interactive bits + Tweaks */
const { useState, useEffect, useMemo } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "billing": "monthly",
  "highlight": "researcher",
  "currency": "USD",
  "showStrike": true,
  "compactCards": false
}/*EDITMODE-END*/;

const PLANS = [
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
    perSeat: true,
    cta: "Set up the lab",
    ctaStyle: "outline",
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

const COMPARE = [
  { group: "Library", rows: [
    { f: "Active projects", v: ["1–2", "5–10", "Unlimited", "Unlimited"] },
    { f: "PDF uploads", v: ["5", "50", "200", "Pooled"] },
    { f: "Paper search across index", v: ["Limited", "Full", "Full + filters", "Full + filters"] },
    { f: "Source previews & citation trail", v: [false, true, true, true] },
  ]},
  { group: "Intelligence", rows: [
    { f: "Chat with papers", v: ["Single", "Multi-paper", "Multi-paper", "Multi-paper"] },
    { f: "Deep Search reports / month", v: ["1 short", "10", "40", "Pooled"] },
    { f: "Writer workspace", v: [false, "Basic", "Full", "Full"] },
    { f: "Bring your own model", v: [false, false, true, true] },
  ]},
  { group: "Output", rows: [
    { f: "BibTeX / Markdown export", v: [false, true, true, true] },
    { f: "Citation styles (APA, MLA, …)", v: [false, "Basic", "All", "All"] },
    { f: "Saved outputs & versions", v: [false, false, true, true] },
  ]},
  { group: "Team & control", rows: [
    { f: "Shared projects & libraries", v: [false, false, false, true] },
    { f: "Admin dashboard & usage", v: [false, false, false, true] },
    { f: "Priority queue for long reports", v: [false, false, false, true] },
    { f: "Single team invoice & billing", v: [false, false, false, true] },
  ]},
];

const FAQ = [
  { q: "Can I switch plans mid-month?",
    a: "Yes. Upgrades prorate immediately and you keep the new limits the same day. Downgrades take effect at the next renewal so you don't lose access mid-paper." },
  { q: "What counts as a Deep Search report?",
    a: "One agentic, multi-hop research run that ends with a synthesized memo and a citation list. Quick chats, single-paper questions, and re-runs of the same query within 24 hours don't burn a credit." },
  { q: "Do my uploads stay private?",
    a: "Always. Documents you upload are scoped to your projects, encrypted at rest, and never used to train shared models. Institution plans add custom retention and regional storage." },
  { q: "Is there a real student discount?",
    a: "Yes — verified through SheerID with a current .edu email or student ID. The Student plan stays at its discounted rate as long as you stay enrolled, re-verified once a year." },
  { q: "What happens when I hit a limit?",
    a: "You'll keep read access to everything you've already added, and we'll prompt you to upgrade or buy a top-up pack. We never silently delete your work." },
  { q: "How does Lab pooling work?",
    a: "All Deep Search credits and PDF capacity become shared resources for the team. The admin dashboard shows who's using what so power users don't quietly drain the pool." },
];

/* ── helpers ── */
const fmt = (n, currency) => {
  if (n == null) return "Custom";
  const sign = currency === "EUR" ? "€" : currency === "GBP" ? "£" : "$";
  return sign + n;
};
const Check = ({ strong }) => (
  <span className={`material-symbols-outlined check-ico mt-[3px] flex-shrink-0 ${strong ? "text-primary" : "text-secondary/80"}`}>check</span>
);

/* ── PLAN CARD ── */
function PlanCard({ plan, billing, currency, highlighted, showStrike, compact }) {
  const price = billing === "annual" ? plan.annual : plan.monthly;
  const strike = billing === "annual" && plan.monthly && plan.annual !== plan.monthly && showStrike;
  const isCustom = price == null;
  const isHi = highlighted === plan.id;

  const cardClass = isHi
    ? "plan-card featured-card bg-primary text-white border border-transparent rounded-2xl"
    : "plan-card bg-surface-container-lowest border border-outline-variant/60 rounded-2xl";

  const headlineColor = isHi ? "text-white" : "text-on-surface";
  const muted = isHi ? "text-white/70" : "text-on-surface-variant";
  const taglineColor = isHi ? "text-on-primary-container" : "text-secondary";

  const cta = plan.ctaStyle === "primary" || isHi
    ? (isHi
        ? "bg-white text-primary hover:opacity-90"
        : "bg-primary text-white hover:opacity-90")
    : "bg-transparent text-on-surface border border-outline/40 hover:bg-primary/5";

  return (
    <div className={`${cardClass} p-6 flex flex-col relative`}>
      {(plan.badge || isHi) && (
        <span className="tag absolute -top-3 left-6 bg-secondary-container text-primary border border-primary-container/20">
          <span className="material-symbols-outlined" style={{fontSize:11}}>workspace_premium</span>
          {plan.badge || "Recommended"}
        </span>
      )}

      <div className="flex items-baseline justify-between">
        <h3 className={`font-headline text-2xl ${headlineColor}`}>{plan.name}</h3>
      </div>
      <p className={`mt-1 text-[13px] italic font-headline ${taglineColor}`}>{plan.tagline}</p>

      <div className="mt-6 flex items-baseline gap-2 min-h-[56px]">
        {isCustom ? (
          <span className={`font-headline text-[44px] leading-none ${headlineColor}`}>Custom</span>
        ) : (
          <>
            <span className={`font-headline text-[44px] leading-none ${headlineColor}`}>{fmt(price, currency)}</span>
            <div className={`flex flex-col text-[11px] leading-tight ${muted}`}>
              {plan.perSeat && <span>/seat</span>}
              <span>/month</span>
              {strike && <span className="line-through opacity-60">{fmt(plan.monthly, currency)}/mo</span>}
            </div>
          </>
        )}
      </div>

      <button className={`mt-5 w-full rounded-full py-2.5 text-sm font-medium pill-btn ${cta}`}>
        {plan.cta}
      </button>

      <p className={`mt-5 text-[11px] uppercase tracking-[0.16em] font-semibold ${muted}`}>What's included</p>
      <p className={`mt-1 text-[12px] ${muted}`}>{plan.bestFor}</p>

      <ul className={`mt-4 space-y-2.5 text-[13px] ${compact ? "text-[12px]" : ""}`}>
        {plan.features.map((f, i) => (
          <li key={i} className="flex gap-2 items-start">
            <Check strong={f.strong && !isHi} />
            <span className={`${isHi ? "text-white/90" : "text-on-surface"} ${f.strong ? "font-medium" : ""}`}>{f.t}</span>
          </li>
        ))}
      </ul>

      <div className={`mt-5 pt-4 border-t ${isHi ? "border-white/15" : "border-outline/15"} text-[11px] ${muted} italic`}>
        {plan.limit}
      </div>
    </div>
  );
}

/* ── COMPARISON CELL ── */
function CmpCell({ v }) {
  if (v === true)  return <span className="material-symbols-outlined text-primary" style={{fontSize:18}}>check</span>;
  if (v === false) return <span className="text-on-surface-variant/40">—</span>;
  return <span className="text-on-surface text-[13px]">{v}</span>;
}

/* ── FAQ ITEM ── */
function FaqItem({ q, a }) {
  return (
    <details className="group py-5">
      <summary className="flex items-start justify-between gap-6 cursor-pointer list-none">
        <span className="font-headline text-[19px] text-on-surface pr-8">{q}</span>
        <span className="material-symbols-outlined chev text-on-surface-variant flex-shrink-0 mt-1">expand_more</span>
      </summary>
      <p className="mt-3 text-[14px] leading-relaxed text-on-surface-variant max-w-[64ch]">{a}</p>
    </details>
  );
}

/* ── APP ── */
function App() {
  const [t, setTweak] = window.useTweaks(TWEAK_DEFAULTS);

  // sync hero billing toggle
  useEffect(() => {
    const m = document.getElementById("bill-monthly");
    const a = document.getElementById("bill-annual");
    if (!m || !a) return;
    const on = "px-5 py-2 rounded-full text-sm font-medium bg-primary text-white";
    const off = "px-5 py-2 rounded-full text-sm font-medium text-on-surface-variant flex items-center gap-2";
    m.className = t.billing === "monthly" ? on : off + " " + (off.includes("flex") ? "" : "flex items-center gap-2");
    a.className = t.billing === "annual"
      ? "px-5 py-2 rounded-full text-sm font-medium bg-primary text-white flex items-center gap-2"
      : off;
    if (t.billing === "annual") {
      a.innerHTML = 'Annually <span class="text-[10px] tracking-wider uppercase font-semibold text-white bg-primary-container/40 px-2 py-0.5 rounded-full">−20%</span>';
    } else {
      a.innerHTML = 'Annually <span class="text-[10px] tracking-wider uppercase font-semibold text-primary bg-secondary-container px-2 py-0.5 rounded-full">−20%</span>';
    }
    m.onclick = () => setTweak("billing", "monthly");
    a.onclick = () => setTweak("billing", "annual");
  }, [t.billing, setTweak]);

  return (
    <>
      {/* Plan grid */}
      {ReactDOM.createPortal(
        <>
          {PLANS.map(p => (
            <PlanCard
              key={p.id}
              plan={p}
              billing={t.billing}
              currency={t.currency}
              highlighted={t.highlight}
              showStrike={t.showStrike}
              compact={t.compactCards}
            />
          ))}
        </>,
        document.getElementById("plan-grid")
      )}

      {/* Comparison body */}
      {ReactDOM.createPortal(
        <>
          {COMPARE.map((g, gi) => (
            <React.Fragment key={gi}>
              <tr className="bg-surface-container/40">
                <td colSpan={5} className="px-6 py-3 text-[11px] tracking-[0.18em] uppercase text-primary font-semibold">{g.group}</td>
              </tr>
              {g.rows.map((r, ri) => (
                <tr key={ri} className="hover:bg-surface-container/30">
                  <td className="px-6 py-3.5 text-on-surface-variant">{r.f}</td>
                  {r.v.map((cell, ci) => (
                    <td key={ci} className="px-3 py-3.5 align-top">
                      <CmpCell v={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </React.Fragment>
          ))}
        </>,
        document.getElementById("compare-body")
      )}

      {/* FAQ */}
      {ReactDOM.createPortal(
        <>{FAQ.map((f, i) => <FaqItem key={i} {...f} />)}</>,
        document.getElementById("faq")
      )}

      {/* Tweaks */}
      <window.TweaksPanel title="Tweaks">
        <window.TweakSection title="Billing & price">
          <window.TweakRadio
            label="Billing cycle"
            value={t.billing}
            onChange={v => setTweak("billing", v)}
            options={[{value:"monthly", label:"Monthly"}, {value:"annual", label:"Annual"}]}
          />
          <window.TweakSelect
            label="Currency"
            value={t.currency}
            onChange={v => setTweak("currency", v)}
            options={[
              {value:"USD", label:"USD ($)"},
              {value:"EUR", label:"EUR (€)"},
              {value:"GBP", label:"GBP (£)"},
            ]}
          />
          <window.TweakToggle
            label="Show monthly price struck through on annual"
            value={t.showStrike}
            onChange={v => setTweak("showStrike", v)}
          />
        </window.TweakSection>

        <window.TweakSection title="Featured plan">
          <window.TweakSelect
            label="Highlight which tier"
            value={t.highlight}
            onChange={v => setTweak("highlight", v)}
            options={[
              {value:"none", label:"None"},
              {value:"free", label:"Free"},
              {value:"student", label:"Student"},
              {value:"researcher", label:"Researcher Pro"},
              {value:"lab", label:"Lab / Team"},
            ]}
          />
        </window.TweakSection>

        <window.TweakSection title="Density">
          <window.TweakToggle
            label="Compact card text"
            value={t.compactCards}
            onChange={v => setTweak("compactCards", v)}
          />
        </window.TweakSection>
      </window.TweaksPanel>
    </>
  );
}

const root = document.createElement("div");
document.body.appendChild(root);
ReactDOM.createRoot(root).render(<App />);
