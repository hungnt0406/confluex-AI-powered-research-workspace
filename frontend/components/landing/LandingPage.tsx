"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import "@/app/landing.css";

const CHAT_HREF = "/chat";
const WRITER_HREF = "/writer";
const PRICING_HREF = "/pricing";

function useAuthedHref(target: string): string {
  const { ready, token } = useAuth();
  if (!ready) return target;
  if (token) return target;
  return `/login?next=${encodeURIComponent(target)}`;
}

const LOGO_STROKES = [
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

function LogoMark({ size = 26, stroke = "#7BAD8A" }: { size?: number; stroke?: string }) {
  return (
    <svg viewBox="0 0 62 60" width={size} height={size} fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
      {LOGO_STROKES.map((d, i) => (
        <path key={i} d={d} stroke={stroke} strokeWidth="1.6" strokeLinecap="round" fill="none" />
      ))}
    </svg>
  );
}

function MIcon({ name, className = "", style }: { name: string; className?: string; style?: React.CSSProperties }) {
  return (
    <span className={`icon ${className}`} style={style} aria-hidden="true">
      {name}
    </span>
  );
}

function TopNav() {
  const [scrolled, setScrolled] = useState(false);
  const { ready, token } = useAuth();
  const chatHref = useAuthedHref(CHAT_HREF);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  const cls = `nav ${scrolled ? "nav-scrolled" : "nav-on-dark"}`;
  const ctaLabel = ready && token ? "Open workspace" : "Start a review";
  return (
    <nav className={cls}>
      <div className="container nav-inner">
        <a href="#top" className="brand-mark" aria-label="Confluex home">
          <LogoMark size={26} />
          <span className="wordmark">confluex</span>
        </a>
        <div className="nav-links">
          <a href="#how">How it works</a>
          <a href="#sources">Sources</a>
          <a href="#sample">Sample output</a>
          <a href="#pricing">Pricing</a>
        </div>
        <Link href={chatHref} className="btn btn-primary btn-sm">
          {ctaLabel}
          <MIcon name="arrow_forward" className="icon-18" />
        </Link>
      </div>
    </nav>
  );
}

const CHAT_SUGGESTIONS = [
  "The impact of LLMs on Academic Integrity",
  "Microplastics in urban soil ecosystems",
  "Policy-driven shifts in remote education",
  "CRISPR delivery in solid tumours",
  "Federated learning under data drift",
  "Heat-island mitigation in tropical cities",
];

const GREETING_SEGMENTS: Array<{ text: string; italic: boolean }> = [
  { text: "To begin our journey through the literature, we must first establish a ", italic: false },
  { text: "precise focal point", italic: true },
  { text: ".", italic: false },
];
const GREETING_FULL_LENGTH = GREETING_SEGMENTS.reduce((n, s) => n + s.text.length, 0);

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

function ChatPreview() {
  const reduced = usePrefersReducedMotion();
  const [typed, setTyped] = useState(GREETING_FULL_LENGTH);
  const [hasMounted, setHasMounted] = useState(false);
  const [chipStart, setChipStart] = useState(0);
  const router = useRouter();
  const chatHref = useAuthedHref(CHAT_HREF);

  useEffect(() => {
    setHasMounted(true);
  }, []);

  const handleChipClick = (topic: string) => {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem("landing.topic", topic);
    }
    router.push(chatHref);
  };

  useEffect(() => {
    if (!hasMounted || reduced) return;
    setTyped(0);
    let n = 0;
    const tick = window.setInterval(() => {
      n += 1;
      setTyped(n);
      if (n >= GREETING_FULL_LENGTH) window.clearInterval(tick);
    }, 28);
    return () => window.clearInterval(tick);
  }, [hasMounted, reduced]);

  useEffect(() => {
    if (reduced) return;
    const rotate = window.setInterval(() => {
      setChipStart((i) => (i + 1) % CHAT_SUGGESTIONS.length);
    }, 2600);
    return () => window.clearInterval(rotate);
  }, [reduced]);

  const visibleChips = [0, 1, 2].map((offset) => {
    const idx = (chipStart + offset) % CHAT_SUGGESTIONS.length;
    return { idx, text: CHAT_SUGGESTIONS[idx] };
  });

  let consumed = 0;
  const greetingNodes = GREETING_SEGMENTS.map((seg, i) => {
    const remaining = Math.max(0, typed - consumed);
    const shown = seg.text.slice(0, Math.min(seg.text.length, remaining));
    consumed += seg.text.length;
    if (!shown) return null;
    return seg.italic ? <em key={i}>{shown}</em> : <React.Fragment key={i}>{shown}</React.Fragment>;
  });
  const typingDone = typed >= GREETING_FULL_LENGTH;

  return (
    <div className="chat-preview">
      <div className="chat-preview-chrome">
        <span className="brand-mark" style={{ gap: 7 }}>
          <LogoMark size={20} />
          <span className="wordmark" style={{ fontSize: 14 }}>confluex</span>
        </span>
        <span className="chat-preview-caps">Live preview</span>
      </div>
      <div className="chat-preview-body">
        <div className="chat-msg">
          <span className="avatar-bubble">
            <MIcon name="school" className="icon-18 icon-fill" />
          </span>
          <div className="chat-msg-body">
            <p className="chat-greeting" aria-label={GREETING_SEGMENTS.map((s) => s.text).join("")}>
              {greetingNodes}
              {!typingDone && <span className="type-caret" aria-hidden="true" />}
            </p>
            <p className="chat-sub">
              Describe your research topic or question in detail. I&apos;ll help you expand your queries and find relevant
              papers.
            </p>
            <div className="chat-chips">
              {visibleChips.map(({ idx, text }, slot) => (
                <button
                  type="button"
                  className="chat-chip chip-fade chip-btn"
                  key={`${slot}-${idx}`}
                  onClick={() => handleChipClick(text)}
                >
                  &ldquo;{text}&rdquo;
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="chat-composer">
        <button type="button" className="chat-icon-btn" aria-label="Upload PDF">
          <MIcon name="add_circle" className="icon-20" />
        </button>
        <span className="chat-composer-placeholder">
          Describe a research topic to begin
          <span className="composer-caret" aria-hidden="true" />
        </span>
        <span className="chat-mode">
          Standard
          <MIcon name="expand_more" style={{ fontSize: 14, marginLeft: 2 }} />
        </span>
        <button type="button" className="chat-send" aria-label="Send">
          <MIcon name="arrow_upward" className="icon-18" />
        </button>
      </div>
      <div className="chat-preview-foot">Secured Academic Session · 225M Papers Indexed</div>
    </div>
  );
}

function Hero() {
  const { ready, token } = useAuth();
  const chatHref = useAuthedHref(CHAT_HREF);
  const ctaLabel = ready && token ? "Open workspace" : "Start a review";
  return (
    <section id="top" className="hero surface-primary">
      <div className="container">
        <div className="hero-grid">
          <div>
            <div className="hero-eyebrow-row">
              <span className="pip"></span>
              <span className="label">AI Research Agent</span>
              <span className="divider"></span>
            </div>

            <h1 className="h-display">
              Literature review,
              <br />
              <span className="serif-italic">grounded in</span> the
              <br />
              papers it actually read.
            </h1>

            <p className="lede" style={{ marginTop: 28 }}>
              Confluex searches Semantic Scholar, arXiv, and PubMed, ranks what matters with composite scoring, and
              writes you a survey you can defend — every <span className="serif-italic">[N]</span> in the draft is
              traceable to an abstract in the local cache.
            </p>

            <div className="hero-actions">
              <Link href={chatHref} className="btn btn-primary">
                {ctaLabel}
                <MIcon name="arrow_forward" className="icon-18" />
              </Link>
              <a href="#how" className="btn btn-ghost">
                <MIcon name="play_arrow" className="icon-18 icon-fill" />
                See how it works
              </a>
              <span className="note">No card · free during beta</span>
            </div>

            <div className="hero-meta">
              <div>
                <div className="num">
                  225M<em>+</em>
                </div>
                <div className="lbl">
                  Papers
                  <br />
                  indexed
                </div>
              </div>
              <div>
                <div className="num">
                  3<em>–5</em>
                </div>
                <div className="lbl">
                  LLM calls
                  <br />
                  per review
                </div>
              </div>
              <div>
                <div className="num">$0.20</div>
                <div className="lbl">
                  Average
                  <br />
                  cost
                </div>
              </div>
            </div>
          </div>

          <aside className="hero-side">
            <ChatPreview />
          </aside>
        </div>
      </div>
    </section>
  );
}

function VideoSlot() {
  return (
    <div className="video-slot">
      <div className="video-slot-chrome">
        <div className="video-chrome-top">
          <span className="left">
            <span className="pip"></span>
            Confluex · Deep Research Max
          </span>
          <span className="caps">Demo recording</span>
        </div>
        <div className="video-slot-body">
          <button className="play-btn" aria-label="Play walkthrough">
            <svg width="22" height="24" viewBox="0 0 22 26" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M21 11.27a2 2 0 0 1 0 3.46l-18 10.39A2 2 0 0 1 0 23.39V2.61A2 2 0 0 1 3 .88l18 10.39Z"
                fill="currentColor"
              />
            </svg>
          </button>
          <div className="note">A two-minute walkthrough lives here.</div>
          <div className="hint">Watch a full Confluex run from topic to defended survey.</div>
        </div>
      </div>
      <div className="video-timecode">00:00 / 02:14</div>
    </div>
  );
}

function VideoSection() {
  return (
    <section id="video" className="surface-paper video-section">
      <div className="container">
        <div className="video-section-head">
          <div>
            <div className="section-eyebrow">
              <span className="dot"></span>
              <span className="num">02</span>
              <span className="line"></span>
              <span>Walkthrough</span>
            </div>
            <h2 className="h-1">
              From a topic to a <span className="serif-italic">defended</span> survey,
              <br />
              in two minutes.
            </h2>
          </div>
          <p className="lede">
            Watch a single run end-to-end — keyword expansion, four parallel searches, the cosine-filter cut, composite
            ranking, the LLM call that writes the actual prose, and the quality-judge handshake that decides whether to
            ship or re-synthesise.
          </p>
        </div>

        <div className="video-section-frame">
          <VideoSlot />
        </div>

        <div className="video-section-foot">
          <span className="mono-tag">
            <span className="pip"></span>Demo recording · 02:14
          </span>
          <span className="mono-tag">
            <span className="pip"></span>Deep Research Max
          </span>
          <span className="mono-tag">
            <span className="pip"></span>Live cache · 225M papers
          </span>
        </div>
      </div>
    </section>
  );
}

function Sources() {
  const items = [
    { icon: "menu_book", name: "Semantic Scholar", tag: "primary api", stat: "200M+", label: "papers, with citation graph" },
    { icon: "article", name: "arXiv", tag: "preprints", stat: "2.4M+", label: "abstracts mirrored locally" },
    { icon: "biotech", name: "PubMed", tag: "biomedical", stat: "36M+", label: "via E-utilities" },
    { icon: "hub", name: "Local index", tag: "specter2 · minilm", stat: "Chroma", label: "vector store, sub-second filter" },
  ];
  return (
    <section id="sources" className="surface-container">
      <div className="container">
        <div className="sources-top">
          <div>
            <div className="section-eyebrow">
              <span className="dot"></span>
              <span className="num">03</span>
              <span className="line"></span>
              <span>Sources</span>
            </div>
            <h2 className="h-1">
              Pulled from the <span className="serif-italic">canon</span>.
              <br />
              Not the open web.
            </h2>
          </div>
          <p className="lede">
            Every Confluex run starts with a parallel search across the three databases serious researchers actually
            trust, plus a local SPECTER2 / MiniLM vector index for sub-second pre-filtering. No SEO blogs. No press
            releases. No hallucinated journals.
          </p>
        </div>

        <div className="sources-grid">
          {items.map((it) => (
            <div className="source-cell" key={it.name}>
              <span className="source-icon">
                <MIcon name={it.icon} className="icon-20 icon-fill" />
              </span>
              <span className="source-tag">{it.tag}</span>
              <div className="source-name">{it.name}</div>
              <div className="source-stat">
                <span className="num">{it.stat}</span>
                {it.label}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

interface Stage {
  num: string;
  title: string;
  icon: string;
  blurb: string;
  bullets: string[];
  llm: boolean;
}

function Pipeline() {
  const stages: Stage[] = [
    {
      num: "Stage 01",
      title: "Search",
      icon: "travel_explore",
      blurb:
        "Parallel queries across S2, arXiv, PubMed, and the local Chroma index. BM25 keyword expansion — no LLM in the loop.",
      bullets: ["BM25 keyword expansion", "Four sources in parallel", "100–500 candidates"],
      llm: false,
    },
    {
      num: "Stage 02",
      title: "Filter",
      icon: "filter_alt",
      blurb:
        "Every abstract is embedded with SPECTER2 or MiniLM and scored by cosine similarity against the topic. Threshold at 0.3.",
      bullets: ["SPECTER2 / MiniLM", "Cosine similarity", "30–100 papers kept"],
      llm: false,
    },
    {
      num: "Stage 03",
      title: "Rank",
      icon: "leaderboard",
      blurb:
        "Composite score: 60% relevance, 20% log-normalised citations, 20% recency. DOI + Jaccard-title dedup, top-N selected.",
      bullets: ["α·relevance + β·log(cites) + γ·recency", "DOI + title Jaccard dedup", "Top 20"],
      llm: false,
    },
    {
      num: "Stage 04",
      title: "Synthesise",
      icon: "auto_stories",
      blurb:
        "One large LLM call assembles the survey: intro, themes, methods, findings, gaps, conclusion. Every claim cited inline as [N].",
      bullets: ["Single GPT-4o call", "Six sections, [N] citations", "Abstract-grounded"],
      llm: true,
    },
    {
      num: "Stage 05",
      title: "Quality",
      icon: "verified",
      blurb:
        "A second, cheaper LLM scores coherence, coverage, citation accuracy, writing. Below 0.7 → feedback loop, max two retries.",
      bullets: ["GPT-4o-mini judge", "Four-axis rubric", "Feedback → re-synth"],
      llm: true,
    },
  ];

  return (
    <section id="how" className="surface-paper">
      <div className="container">
        <div className="pipeline-head">
          <div>
            <div className="section-eyebrow">
              <span className="dot"></span>
              <span className="num">04</span>
              <span className="line"></span>
              <span>How it works</span>
            </div>
            <h2 className="h-1">
              Five stages.
              <br />
              <span className="serif-italic">Two</span> use a language model.
            </h2>
          </div>
          <p className="lede">
            Most &ldquo;AI research&rdquo; tools call a language model for every step and bill you for it. Confluex
            reserves the LLM for what it&apos;s actually good at — writing — and uses embeddings, BM25, and traditional
            NLP for the rest. The result is 3–5 calls per review instead of 50–100, with the same model behind both.
          </p>
        </div>

        <div className="pipeline-grid">
          {stages.map((s) => (
            <article className="stage" key={s.num}>
              <div className="stage-head">
                <span className="stage-num">{s.num}</span>
                <span className={`stage-icon ${s.llm ? "is-llm" : ""}`}>
                  <MIcon name={s.icon} className="icon-18 icon-fill" />
                </span>
              </div>
              <h3 className="stage-title">{s.title}</h3>
              <p className="stage-blurb">{s.blurb}</p>
              <ul className="stage-list">
                {s.bullets.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
              <div className="stage-tag-row">
                <span className={`mono-tag ${s.llm ? "is-primary" : ""}`}>
                  <span className="pip"></span>
                  {s.llm ? "LLM" : "No LLM"}
                </span>
              </div>
            </article>
          ))}
        </div>

        <div className="pipeline-cost">
          <div className="stat">
            <span className="label">Legacy stacks</span>
            <span className="val">~50–100</span>
            <span>LLM calls / review · $2–5</span>
          </div>
          <span className="sep"></span>
          <div className="stat">
            <span className="label">Confluex</span>
            <span className="val">3–5</span>
            <span>LLM calls / review · $0.10–0.30</span>
          </div>
          <span className="sep"></span>
          <div className="stat">
            <span className="label">Net</span>
            <span className="val">17×</span>
            <span>fewer LLM calls, same model</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function QRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="qrow">
      <span className="label">{label}</span>
      <span className="bar">
        <i style={{ width: `${value * 100}%` }}></i>
      </span>
      <span className="val">{value.toFixed(2)}</span>
    </div>
  );
}

function Sample() {
  return (
    <section id="sample" className="surface-container">
      <div className="container">
        <div className="sample-head">
          <div>
            <div className="section-eyebrow">
              <span className="dot"></span>
              <span className="num">05</span>
              <span className="line"></span>
              <span>Sample output</span>
            </div>
            <h2 className="h-1">
              An excerpt,
              <br />
              <span className="serif-italic">not</span> a mood board.
            </h2>
          </div>
          <p className="lede">
            Every review exports as <strong style={{ fontWeight: 600 }}>.docx</strong>,
            <strong style={{ fontWeight: 600 }}> .tex</strong>, and a compiled
            <strong style={{ fontWeight: 600 }}> .pdf</strong>. Citations are numbered, traceable, and survive an
            advisor&apos;s red pen — because each one comes from an abstract the system actually read.
          </p>
        </div>

        <article className="doc">
          <header className="doc-header">
            <span className="meta">
              <span className="pip"></span>
              <span className="caps">Review · 2026-05-13</span>
            </span>
            <span className="meta">
              <span className="caps">Model · gpt-4o · 20 papers</span>
            </span>
            <span className="meta">
              <span className="caps">Quality · 0.87 avg</span>
            </span>
          </header>

          <div className="doc-main">
            <h3 className="doc-title">2.&nbsp; Thematic Analysis of Retrieval-Augmented Approaches</h3>
            <span className="doc-section-label">Section excerpt</span>

            <p>
              The first wave of retrieval-augmented generation systems treated retrieval as a one-shot upstream step,
              concatenating top-<i>k</i> passages into a fixed context window before generation
              <span className="cite">[1]</span>. Subsequent work relaxes this rigidity: <i>iterative</i> retrievers
              re-query the corpus after each generation step<span className="cite">[3]</span>, while{" "}
              <i>self-reflective</i> variants emit explicit retrieval tokens to decide <i>when</i> additional context is
              warranted<span className="cite">[7]</span>.
            </p>

            <p>
              For long-form scientific writing the trade-off is sharper. Static retrieval is fast and reproducible but
              tends to over-represent the first few sub-topics; iterative schemes adapt but compound latency and citation
              drift<span className="cite">[4,&nbsp;9]</span>. A growing body of evidence suggests that the
              highest-quality surveys come not from richer prompting but from <i>better candidate sets</i>: composite
              scoring functions over relevance, citation count, and recency consistently outperform pure semantic
              ranking on coverage and novelty<span className="cite">[12,&nbsp;14]</span>.
            </p>

            <p style={{ color: "var(--on-surface-variant)" }}>
              <i>… continues for five more sections — methodology comparison, key findings, gaps, and conclusion.</i>
            </p>
          </div>

          <aside className="doc-side">
            <div>
              <h4>References (excerpt)</h4>
              <div className="doc-cites">
                <div className="doc-cite">
                  <span className="n">[1]</span>
                  <div>
                    <div className="ref-title">
                      Lewis et&nbsp;al. — Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks
                    </div>
                    <div className="ref-meta">NeurIPS 2020 · 4,812 citations</div>
                  </div>
                </div>
                <div className="doc-cite">
                  <span className="n">[3]</span>
                  <div>
                    <div className="ref-title">Trivedi et&nbsp;al. — Interleaving Retrieval with Chain-of-Thought</div>
                    <div className="ref-meta">ACL 2023 · 612 citations</div>
                  </div>
                </div>
                <div className="doc-cite">
                  <span className="n">[7]</span>
                  <div>
                    <div className="ref-title">Asai et&nbsp;al. — Self-RAG: Learning to Retrieve, Generate, and Critique</div>
                    <div className="ref-meta">ICLR 2024 · 387 citations</div>
                  </div>
                </div>
              </div>
            </div>

            <div>
              <h4>Quality scores</h4>
              <div className="doc-quality">
                <QRow label="Coherence" value={0.88} />
                <QRow label="Coverage" value={0.82} />
                <QRow label="Citations" value={0.91} />
                <QRow label="Writing" value={0.85} />
              </div>
            </div>
          </aside>
        </article>
      </div>
    </section>
  );
}

function Pricing() {
  return (
    <section id="pricing" className="surface-paper">
      <div className="container">
        <div className="pricing-head">
          <div>
            <div className="section-eyebrow">
              <span className="dot"></span>
              <span className="num">06</span>
              <span className="line"></span>
              <span>Pricing</span>
            </div>
            <h2 className="h-1">
              Pennies,
              <br />
              not <span className="serif-italic">months</span>.
            </h2>
          </div>
          <p className="lede">
            A traditional literature review costs you two to four months of focused time and a stack of irrelevant PDFs.
            A Confluex review costs roughly the price of a coffee — and the difference is almost entirely the LLM-call
            count.
          </p>
        </div>

        <div className="compare">
          <div className="compare-col them">
            <span className="mono-tag">
              <span className="pip"></span>Doing it the old way
            </span>
            <h3 className="compare-headline">Two–four months of reading</h3>
            <div className="compare-price">
              <span className="num">$2–5</span>
              <span className="unit">per LLM-heavy review · 50–100 calls</span>
            </div>
            <ul className="compare-list">
              <li>
                <span className="mark">close</span>
                <span>LLM called at every pipeline step — costs balloon with paper count.</span>
              </li>
              <li>
                <span className="mark">close</span>
                <span>Citations frequently hallucinated or paraphrased without source.</span>
              </li>
              <li>
                <span className="mark">close</span>
                <span>~60% of researcher time spent on papers that turn out to be irrelevant.</span>
              </li>
              <li>
                <span className="mark">close</span>
                <span>Advisor feedback triggers a full re-run from scratch.</span>
              </li>
            </ul>
          </div>

          <div className="compare-col us">
            <span className="mono-tag is-primary">
              <span className="pip"></span>With Confluex
            </span>
            <h3 className="compare-headline">An evening of refinement</h3>
            <div className="compare-price">
              <span className="num">
                $0.20 <em>avg.</em>
              </span>
              <span className="unit">per review · 3–5 calls</span>
            </div>
            <ul className="compare-list">
              <li>
                <span className="mark">check</span>
                <span>LLM reserved for synthesis &amp; quality scoring — everything else is embeddings + NLP.</span>
              </li>
              <li>
                <span className="mark">check</span>
                <span>
                  Every <span style={{ fontFamily: "var(--font-headline)", fontStyle: "italic" }}>[N]</span> maps to a
                  real paper in the local cache.
                </span>
              </li>
              <li>
                <span className="mark">check</span>
                <span>Pre-filter at 0.3 cosine throws out the noise before you see it.</span>
              </li>
              <li>
                <span className="mark">check</span>
                <span>Advisor feedback re-uses the cached paper set — no second search bill.</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  const { ready, token } = useAuth();
  const chatHref = useAuthedHref(CHAT_HREF);
  const writerHref = useAuthedHref(WRITER_HREF);
  const ctaLabel = ready && token ? "Open workspace" : "Start a review";
  return (
    <section className="surface-container">
      <div className="container cta-wrap">
        <div className="section-eyebrow" style={{ marginBottom: 24 }}>
          <span className="dot"></span>
          <span className="num">07</span>
          <span className="line"></span>
          <span>Get started</span>
        </div>
        <h2 className="h-display">
          Stop reading papers
          <br />
          <span className="serif-italic">you didn&apos;t</span> need
          <br />
          to read.
        </h2>

        <div className="cta-actions">
          <Link href={chatHref} className="btn btn-primary">
            {ctaLabel}
            <MIcon name="arrow_forward" className="icon-18" />
          </Link>
          <a href="#how" className="btn btn-ghost">
            Re-read how it works
          </a>
          <span style={{ fontSize: 12, color: "var(--hint)", marginLeft: 4 }}>no card · free during beta</span>
        </div>

        <div className="cta-meta">
          <div className="url">
            <Link href={chatHref}>Research workspace</Link>
            &nbsp;·&nbsp;
            <Link href={writerHref}>Writer beta</Link>
            &nbsp;·&nbsp;
            <Link href={PRICING_HREF}>Plans</Link>
          </div>
          <div className="colophon">Confluex · AI20K-026 · Built with LangGraph + FastAPI + Next.js</div>
        </div>
      </div>
    </section>
  );
}

export default function LandingPage() {
  useEffect(() => {
    const body = document.body;
    const html = document.documentElement;
    const hadHScreen = body.classList.contains("h-screen");
    const hadOverflowHidden = body.classList.contains("overflow-hidden");
    body.classList.remove("h-screen", "overflow-hidden");
    body.classList.add("landing-active");
    html.classList.add("landing-active");
    return () => {
      body.classList.remove("landing-active");
      html.classList.remove("landing-active");
      if (hadHScreen) body.classList.add("h-screen");
      if (hadOverflowHidden) body.classList.add("overflow-hidden");
    };
  }, []);

  return (
    <div className="landing-root">
      <TopNav />
      <main>
        <Hero />
        <VideoSection />
        <Sources />
        <Pipeline />
        <Sample />
        <Pricing />
        <Footer />
      </main>
    </div>
  );
}
