"use client";

import dynamic from "next/dynamic";
import {
  ChangeEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useAuth } from "@/components/AuthProvider";
import {
  ApiError,
  CitationGraph as CitationGraphPayload,
  CitationGraphPaper,
  ProjectPaper,
  fetchPaperCitationGraph,
} from "@/lib/api";

// react-force-graph-2d touches `window` and a Canvas element on import, so it
// must be loaded only in the browser.
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => null,
});

// ─── Node / link kind constants ─────────────────────────────────────────────

const SEED_KIND = "seed" as const;
const REFERENCE_KIND = "reference" as const;
const CITED_BY_KIND = "cited_by" as const;

type GraphNodeKind = typeof SEED_KIND | typeof REFERENCE_KIND | typeof CITED_BY_KIND;

type GraphNode = {
  id: string;
  kind: GraphNodeKind;
  title: string;
  authors: string[];
  year: number | null;
  citationCount: number | null;
  url: string | null;
  /** Normalised citation weight [0, 1] across all non-seed nodes. */
  weight: number;
};

type GraphLink = {
  source: string;
  target: string;
  /** Connection strength [0, 1] – drives link distance and opacity. */
  strength: number;
};

type GraphData = {
  nodes: GraphNode[];
  links: GraphLink[];
};

type CitationGraphProps = {
  projectId: string;
  papers: ProjectPaper[];
};

type LoadState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string; status: number | null }
  | { kind: "loaded"; data: CitationGraphPayload };

// ─── Limits ──────────────────────────────────────────────────────────────────

const SEED_LIMIT = 20;
const MAX_CITED_BY = 10;
const MAX_REFERENCES = 20;

// ─── Visual constants ────────────────────────────────────────────────────────

/** Seed paper radius (canvas units). */
const SEED_RADIUS = 18;
/** Minimum radius for leaf nodes (canvas units). */
const MIN_NODE_RADIUS = 5;
/** Maximum radius for a leaf node (canvas units). */
const MAX_NODE_RADIUS = 14;

/** Base link distance for the weakest connection (pixels). */
const LINK_DIST_FAR = 160;
/** Base link distance for the strongest connection (pixels). */
const LINK_DIST_NEAR = 60;

/** Seed node border colour. */
const SEED_STROKE = "#35824B";
/** Seed node fill. */
const SEED_FILL = "#3daa5c";
/** Reference node hue (green family). */
const REF_HUE_START = "#7BAD8A";
/** Cited-by node hue (amber family). */
const CITE_HUE_START = "#F59E0B";

// ─── Component ───────────────────────────────────────────────────────────────

export default function CitationGraph({ projectId, papers }: CitationGraphProps) {
  const { token } = useAuth();
  const [seedPaperId, setSeedPaperId] = useState<string>(() => firstResolvablePaperId(papers));
  const [loadState, setLoadState] = useState<LoadState>({ kind: "idle" });
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [containerSize, setContainerSize] = useState<{ width: number; height: number }>({
    width: 0,
    height: 0,
  });
  const requestIdRef = useRef(0);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphRef = useRef<any>(null);

  const seedPaper = useMemo(
    () => papers.find((paper) => paper.id === seedPaperId) ?? null,
    [papers, seedPaperId],
  );
  const seedIsResolvable = seedPaper ? isResolvablePaper(seedPaper) : false;

  // Keep seed paper valid when the papers list changes.
  useEffect(() => {
    if (!papers.some((paper) => paper.id === seedPaperId)) {
      setSeedPaperId(firstResolvablePaperId(papers));
    }
  }, [papers, seedPaperId]);

  // ResizeObserver to track container dimensions.
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      setContainerSize({ width: Math.floor(width), height: Math.floor(height) });
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const loadGraph = useCallback(async () => {
    if (!token || !seedPaper || !seedIsResolvable) return;
    const requestId = ++requestIdRef.current;
    setLoadState({ kind: "loading" });
    try {
      const payload = await fetchPaperCitationGraph(projectId, seedPaper.id, token, {
        limit: SEED_LIMIT,
      });
      if (requestId !== requestIdRef.current) return;
      setLoadState({ kind: "loaded", data: payload });
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      const apiError = err instanceof ApiError ? err : null;
      setLoadState({
        kind: "error",
        message: err instanceof Error ? err.message : "Failed to load citation graph.",
        status: apiError?.status ?? null,
      });
    }
  }, [projectId, seedIsResolvable, seedPaper, token]);

  useEffect(() => {
    if (!seedPaper) {
      setLoadState({ kind: "idle" });
      return;
    }
    if (!seedIsResolvable) {
      setLoadState({
        kind: "error",
        message:
          "This paper has no Semantic Scholar id, arXiv id, or DOI, so a citation graph cannot be resolved.",
        status: 400,
      });
      return;
    }
    void loadGraph();
  }, [loadGraph, seedIsResolvable, seedPaper]);

  const graphData = useMemo<GraphData | null>(() => {
    if (loadState.kind !== "loaded" || !seedPaper) return null;
    return buildGraphData(seedPaper, loadState.data);
  }, [loadState, seedPaper]);

  // After graph data loads, inject custom D3 forces then zoom-to-fit.
  useEffect(() => {
    if (!graphData || !graphRef.current) return;

    const fg = graphRef.current;

    // Variable link distance: highly-cited papers sit closer to the seed.
    fg.d3Force("link")
      ?.distance((link: GraphLink) => {
        const strength = link.strength ?? 0.5;
        // strength=1 (very cited) → NEAR; strength=0 (unknown) → FAR
        return LINK_DIST_FAR - strength * (LINK_DIST_FAR - LINK_DIST_NEAR);
      })
      .strength((link: GraphLink) => {
        // Stronger pull for highly-cited papers so they actually reach their target distance.
        return 0.3 + (link.strength ?? 0.5) * 0.5;
      });

    // Stronger repulsion to spread nodes apart clearly.
    fg.d3Force("charge")?.strength(-220);

    // Re-heat so the new force config takes effect.
    fg.d3ReheatSimulation();

    // Zoom-to-fit after the simulation settles.
    const timeout = setTimeout(() => {
      fg.zoomToFit?.(500, 40);
    }, 800);
    return () => clearTimeout(timeout);
  }, [graphData]);

  const onSeedChange = useCallback((event: ChangeEvent<HTMLSelectElement>) => {
    setSeedPaperId(event.target.value);
  }, []);

  const onNodeClick = useCallback((rawNode: object) => {
    const node = rawNode as GraphNode;
    if (!node.url) return;
    if (typeof window !== "undefined") {
      window.open(node.url, "_blank", "noopener,noreferrer");
    }
  }, []);

  // Custom canvas rendering for nodes.
  const nodeCanvasObject = useCallback(
    (rawNode: object, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const node = rawNode as GraphNode & { x?: number; y?: number };
      if (node.x == null || node.y == null) return;

      const radius = nodeRadius(node);
      const fill = nodeFill(node, graphData);
      const { x, y } = node;

      ctx.save();

      if (node.kind === SEED_KIND) {
        // Outer glow ring.
        const grd = ctx.createRadialGradient(x, y, radius * 0.6, x, y, radius * 2.2);
        grd.addColorStop(0, "rgba(53,170,92,0.35)");
        grd.addColorStop(1, "rgba(53,170,92,0)");
        ctx.beginPath();
        ctx.arc(x, y, radius * 2.2, 0, Math.PI * 2);
        ctx.fillStyle = grd;
        ctx.fill();

        // Border ring.
        ctx.beginPath();
        ctx.arc(x, y, radius + 3, 0, Math.PI * 2);
        ctx.strokeStyle = SEED_STROKE;
        ctx.lineWidth = 2.5 / globalScale;
        ctx.stroke();
      }

      // Main circle.
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = fill;
      ctx.fill();

      // Subtle inner border for non-seed nodes.
      if (node.kind !== SEED_KIND) {
        ctx.strokeStyle = "rgba(255,255,255,0.18)";
        ctx.lineWidth = 1 / globalScale;
        ctx.stroke();
      }

      // Label – only at high zoom or for seed.
      const labelThreshold = node.kind === SEED_KIND ? 0 : 0.7;
      if (globalScale >= labelThreshold) {
        const maxChars = node.kind === SEED_KIND ? 28 : 18;
        const label = truncate(node.title, maxChars);
        const fontSize = node.kind === SEED_KIND
          ? Math.max(10 / globalScale, 3.5)
          : Math.max(8 / globalScale, 2.5);
        ctx.font = `${node.kind === SEED_KIND ? "600 " : ""}${fontSize}px Inter, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        // Background pill for readability.
        const textWidth = ctx.measureText(label).width;
        const pad = fontSize * 0.4;
        const pillH = fontSize + pad * 2;
        const pillY = y + radius + pillH * 0.6;

        ctx.fillStyle = "rgba(10,14,20,0.72)";
        ctx.beginPath();
        ctx.roundRect?.(
          x - textWidth / 2 - pad,
          pillY - pillH / 2,
          textWidth + pad * 2,
          pillH,
          pillH / 2,
        );
        ctx.fill();

        ctx.fillStyle = node.kind === SEED_KIND ? "#ffffff" : "rgba(220,230,220,0.9)";
        ctx.fillText(label, x, pillY);
      }

      ctx.restore();
    },
    [graphData],
  );

  // Custom link canvas rendering with variable opacity and width.
  const linkCanvasObject = useCallback(
    (rawLink: object, ctx: CanvasRenderingContext2D) => {
      const link = rawLink as GraphLink & {
        source: GraphNode & { x?: number; y?: number };
        target: GraphNode & { x?: number; y?: number };
      };
      const { source, target } = link;
      if (
        source.x == null ||
        source.y == null ||
        target.x == null ||
        target.y == null
      )
        return;

      const strength = link.strength ?? 0.5;
      const opacity = 0.12 + strength * 0.35;
      const width = 0.5 + strength * 2;

      // Determine link colour from target node kind.
      const targetKind =
        typeof target === "object" && "kind" in target
          ? (target as GraphNode).kind
          : REFERENCE_KIND;
      const baseColor =
        targetKind === CITED_BY_KIND
          ? `rgba(245, 158, 11, ${opacity.toFixed(2)})`
          : `rgba(53, 170, 92, ${opacity.toFixed(2)})`;

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.lineTo(target.x, target.y);
      ctx.strokeStyle = baseColor;
      ctx.lineWidth = width;
      ctx.stroke();
      ctx.restore();
    },
    [],
  );

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      {/* Seed paper selector */}
      <div className="space-y-1.5">
        <label className="text-[10px] font-bold uppercase tracking-widest text-on-surface">
          Seed paper
        </label>
        <select
          value={seedPaperId}
          onChange={onSeedChange}
          disabled={papers.length === 0}
          className="h-9 w-full rounded-lg border border-outline/30 bg-surface-container-low px-2 text-[11px] text-on-surface outline-none transition-colors focus:border-primary/40 disabled:opacity-50"
          aria-label="Choose a seed paper for the citation graph"
        >
          {papers.length === 0 ? (
            <option value="">No papers available</option>
          ) : (
            papers.map((paper) => (
              <option key={paper.id} value={paper.id} disabled={!isResolvablePaper(paper)}>
                {truncate(paper.title, 80)}
                {!isResolvablePaper(paper) ? " — no DOI/arXiv id" : ""}
              </option>
            ))
          )}
        </select>
      </div>

      {/* Graph canvas */}
      <div
        ref={containerRef}
        className="relative flex-1 min-h-[320px] overflow-hidden rounded-xl border border-outline/30 bg-[#0a0e14]"
      >
        {loadState.kind === "loading" && (
          <CenterMessage>
            <div className="flex items-center gap-2 text-[11px] text-hint">
              <span className="material-symbols-outlined animate-spin text-base">
                progress_activity
              </span>
              Resolving citation neighborhood…
            </div>
          </CenterMessage>
        )}
        {loadState.kind === "error" && (
          <CenterMessage>
            <div className="max-w-[260px] space-y-2 text-center">
              <p className="text-[11px] text-on-surface">
                {humanizeCitationError(loadState.message, loadState.status)}
              </p>
              {seedIsResolvable && (
                <button
                  type="button"
                  onClick={() => void loadGraph()}
                  className="inline-flex h-7 items-center justify-center rounded-md border border-outline/30 px-2 text-[10px] font-medium text-on-surface transition-colors hover:bg-primary/5"
                >
                  Retry
                </button>
              )}
            </div>
          </CenterMessage>
        )}
        {loadState.kind === "idle" && papers.length === 0 && (
          <CenterMessage>
            <p className="max-w-[240px] text-center text-[11px] text-hint">
              Run the discovery pipeline or upload a PDF to see a citation graph.
            </p>
          </CenterMessage>
        )}
        {loadState.kind === "loaded" && graphData && containerSize.width > 0 && (
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            width={containerSize.width}
            height={containerSize.height}
            backgroundColor="rgba(0,0,0,0)"
            // Node appearance delegated to canvas renderer.
            nodeCanvasObject={nodeCanvasObject}
            nodeCanvasObjectMode={() => "replace"}
            // Link appearance delegated to canvas renderer.
            linkCanvasObject={linkCanvasObject}
            linkCanvasObjectMode={() => "replace"}
            // Pointer area includes the label pill below the node.
            nodePointerAreaPaint={(rawNode, color, ctx) => {
              const node = rawNode as GraphNode & { x?: number; y?: number };
              if (node.x == null || node.y == null) return;
              const r = nodeRadius(node) + 8;
              ctx.beginPath();
              ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
              ctx.fillStyle = color;
              ctx.fill();
            }}
            // D3 force simulation config.
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.35}
            cooldownTicks={180}
            warmupTicks={30}
            // Node interactions.
            onNodeClick={onNodeClick}
            nodeLabel={(rawNode: object) => buildNodeTooltip(rawNode as GraphNode)}
          />
        )}

        {/* Stats overlay */}
        {loadState.kind === "loaded" && graphData && (
          <div className="pointer-events-none absolute bottom-2 right-2 flex flex-col items-end gap-0.5">
            <span className="rounded-md bg-black/50 px-1.5 py-0.5 text-[9px] text-hint/70 backdrop-blur-sm">
              {graphData.nodes.length - 1} related papers
            </span>
          </div>
        )}
      </div>

      <Legend />
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function CenterMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center px-4">
      {children}
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[10px] text-hint">
      <LegendDot label="Seed paper" color="#3daa5c" />
      <LegendDot label="References" color="#7BAD8A" />
      <LegendDot label="Cited by" color="#F59E0B" />
      <span className="ml-auto opacity-70">size = citation count · color brightness = recency</span>
    </div>
  );
}

function LegendDot({ label, color }: { label: string; color: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span
        className="inline-block h-2.5 w-2.5 rounded-full"
        style={{ background: color }}
      />
      <span>{label}</span>
    </span>
  );
}

// ─── Graph data builder ───────────────────────────────────────────────────────

function buildGraphData(seedPaper: ProjectPaper, payload: CitationGraphPayload): GraphData {
  const seedId = `seed:${seedPaper.id}`;

  const cappedCitedBy = payload.cited_by.slice(0, MAX_CITED_BY);
  const cappedReferences = payload.references.slice(0, MAX_REFERENCES);

  // Collect all citation counts to normalise weights.
  const allCounts: number[] = [];
  for (const p of [...cappedCitedBy, ...cappedReferences]) {
    if (typeof p.citation_count === "number") allCounts.push(p.citation_count);
  }
  const maxCount = allCounts.length > 0 ? Math.max(...allCounts) : 1;

  const nodes: GraphNode[] = [
    {
      id: seedId,
      kind: SEED_KIND,
      title: seedPaper.title,
      authors: seedPaper.authors ?? [],
      year: seedPaper.year ?? null,
      citationCount: seedPaper.citation_count ?? payload.citation_count ?? null,
      url: seedPaper.source_url ?? null,
      weight: 1,
    },
  ];
  const links: GraphLink[] = [];
  const seenIds = new Set<string>([seedId]);

  cappedCitedBy.forEach((paper, index) => {
    const id = relatedNodeId(paper, `cited:${index}`);
    if (seenIds.has(id)) return;
    seenIds.add(id);
    const weight = normaliseWeight(paper.citation_count, maxCount);
    nodes.push(toGraphNode(paper, id, CITED_BY_KIND, weight));
    links.push({ source: id, target: seedId, strength: weight });
  });

  cappedReferences.forEach((paper, index) => {
    const id = relatedNodeId(paper, `ref:${index}`);
    if (seenIds.has(id)) return;
    seenIds.add(id);
    const weight = normaliseWeight(paper.citation_count, maxCount);
    nodes.push(toGraphNode(paper, id, REFERENCE_KIND, weight));
    links.push({ source: seedId, target: id, strength: weight });
  });

  return { nodes, links };
}

function normaliseWeight(count: number | null | undefined, max: number): number {
  if (count == null || max <= 0) return 0.3;
  // Logarithmic normalisation so highly-cited papers don't dominate.
  const logVal = Math.log10(count + 1);
  const logMax = Math.log10(max + 1);
  return logMax > 0 ? Math.min(1, logVal / logMax) : 0.3;
}

function relatedNodeId(paper: CitationGraphPaper, fallback: string): string {
  if (paper.source_paper_id) return `s2:${paper.source_paper_id}`;
  if (paper.doi) return `doi:${paper.doi}`;
  return fallback;
}

function toGraphNode(
  paper: CitationGraphPaper,
  id: string,
  kind: GraphNodeKind,
  weight: number,
): GraphNode {
  return {
    id,
    kind,
    title: paper.title,
    authors: paper.authors,
    year: paper.year,
    citationCount: paper.citation_count,
    url: paper.source_url,
    weight,
  };
}

// ─── Visual helpers ───────────────────────────────────────────────────────────

function nodeRadius(node: GraphNode): number {
  if (node.kind === SEED_KIND) return SEED_RADIUS;
  // Map normalised weight → radius in [MIN, MAX].
  return MIN_NODE_RADIUS + node.weight * (MAX_NODE_RADIUS - MIN_NODE_RADIUS);
}

/**
 * Returns the fill colour for a node.
 *
 * - Seed: solid green.
 * - Reference / cited-by: base hue blended with year-intensity brightness.
 *   Newer publications are more vivid; older ones fade toward the background.
 */
function nodeFill(node: GraphNode, graphData: GraphData | null): string {
  if (node.kind === SEED_KIND) return SEED_FILL;

  const yearRange = graphData ? computeYearRange(graphData) : { min: 2010, max: new Date().getFullYear() };
  const intensity = yearIntensity(node.year, yearRange);

  if (node.kind === CITED_BY_KIND) {
    return blendOver(CITE_HUE_START, intensity);
  }
  return blendOver(REF_HUE_START, intensity);
}

function computeYearRange(graphData: GraphData): { min: number; max: number } {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (const node of graphData.nodes) {
    if (node.year == null) continue;
    if (node.year < min) min = node.year;
    if (node.year > max) max = node.year;
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    const fallback = new Date().getFullYear();
    return { min: fallback - 10, max: fallback };
  }
  if (min === max) return { min: min - 1, max: max };
  return { min, max };
}

function yearIntensity(year: number | null, range: { min: number; max: number }): number {
  if (year == null) return 0.4;
  const span = range.max - range.min;
  if (span <= 0) return 0.7;
  return Math.min(1, Math.max(0.2, (year - range.min) / span));
}

function blendOver(baseHex: string, intensity: number): string {
  const { r, g, b } = hexToRgb(baseHex);
  // alpha maps intensity [0.2, 1.0] → [0.30, 0.95]
  const alpha = 0.30 + intensity * 0.65;
  return `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(2)})`;
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const normalized = hex.replace("#", "");
  const value = parseInt(normalized, 16);
  return {
    r: (value >> 16) & 0xff,
    g: (value >> 8) & 0xff,
    b: value & 0xff,
  };
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────

function buildNodeTooltip(node: GraphNode): string {
  const authorPreview = node.authors.slice(0, 2).join(", ");
  const moreAuthors = node.authors.length > 2 ? ` +${node.authors.length - 2}` : "";
  const yearLabel = node.year ? ` (${node.year})` : "";
  const citationLabel =
    node.citationCount != null ? ` · ${node.citationCount.toLocaleString()} citations` : "";
  return `${escapeHtml(node.title)}${yearLabel}\n${escapeHtml(authorPreview)}${moreAuthors}${citationLabel}`;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ─── Utility ──────────────────────────────────────────────────────────────────

function truncate(value: string, max: number): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

function isResolvablePaper(paper: ProjectPaper): boolean {
  if (paper.source === "semantic_scholar" && paper.source_paper_id) return true;
  if (paper.source === "arxiv" && (paper.source_paper_id || paper.source_url)) return true;
  if (paper.doi) return true;
  return false;
}

function firstResolvablePaperId(papers: ProjectPaper[]): string {
  return papers.find(isResolvablePaper)?.id ?? papers[0]?.id ?? "";
}

function humanizeCitationError(message: string, status: number | null): string {
  if (status === 400) {
    return message || "This paper can't be resolved exactly upstream.";
  }
  if (status === 404) {
    return "Semantic Scholar couldn't find an exact match for this paper.";
  }
  if (status === 502) {
    return "Semantic Scholar is unavailable right now. Please retry in a moment.";
  }
  return message || "Failed to load citation graph.";
}
