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

// react-force-graph-2d touches `window` and a Canvas element on import, so it has
// to be loaded only in the browser. Next.js `dynamic` with `ssr: false` is the
// canonical way to do this.
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => null,
});

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
};

type GraphLink = {
  source: string;
  target: string;
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

const SEED_LIMIT = 20;
const MAX_CITED_BY = 10;
const MAX_REFERENCES = 20;

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

  const seedPaper = useMemo(
    () => papers.find((paper) => paper.id === seedPaperId) ?? null,
    [papers, seedPaperId],
  );
  const seedIsResolvable = seedPaper ? isResolvablePaper(seedPaper) : false;

  useEffect(() => {
    if (!papers.some((paper) => paper.id === seedPaperId)) {
      setSeedPaperId(firstResolvablePaperId(papers));
    }
  }, [papers, seedPaperId]);

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

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
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

      <div
        ref={containerRef}
        className="relative flex-1 min-h-[320px] overflow-hidden rounded-xl border border-outline/30 bg-surface-container-low"
      >
        {loadState.kind === "loading" && (
          <CenterMessage>
            <div className="flex items-center gap-2 text-[11px] text-hint">
              <span className="material-symbols-outlined animate-spin text-base">progress_activity</span>
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
            graphData={graphData}
            width={containerSize.width}
            height={containerSize.height}
            backgroundColor="rgba(0,0,0,0)"
            nodeRelSize={4}
            nodeVal={(rawNode: object) => nodeRadius(rawNode as GraphNode)}
            nodeColor={(rawNode: object) => nodeColor(rawNode as GraphNode, graphData)}
            nodeLabel={(rawNode: object) => buildNodeTooltip(rawNode as GraphNode)}
            linkColor={() => "rgba(53,130,75,0.25)"}
            linkWidth={1}
            cooldownTicks={120}
            warmupTicks={20}
            onNodeClick={onNodeClick}
          />
        )}
      </div>

      <Legend />
    </div>
  );
}

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
      <LegendDot label="Seed paper" colorClass="bg-primary" />
      <LegendDot label="Reference" colorClass="bg-primary/60" />
      <LegendDot label="Cited by" colorClass="bg-amber-500/80" />
      <span className="ml-auto opacity-80">node size = citation count</span>
    </div>
  );
}

function LegendDot({ label, colorClass }: { label: string; colorClass: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`inline-block h-2 w-2 rounded-full ${colorClass}`} />
      <span>{label}</span>
    </span>
  );
}

function buildGraphData(seedPaper: ProjectPaper, payload: CitationGraphPayload): GraphData {
  const seedId = `seed:${seedPaper.id}`;

  const cappedCitedBy = payload.cited_by.slice(0, MAX_CITED_BY);
  const cappedReferences = payload.references.slice(0, MAX_REFERENCES);

  const nodes: GraphNode[] = [
    {
      id: seedId,
      kind: SEED_KIND,
      title: seedPaper.title,
      authors: seedPaper.authors ?? [],
      year: seedPaper.year ?? null,
      citationCount: seedPaper.citation_count ?? payload.citation_count ?? null,
      url: seedPaper.source_url ?? null,
    },
  ];
  const links: GraphLink[] = [];
  const seenIds = new Set<string>([seedId]);

  cappedCitedBy.forEach((paper, index) => {
    const id = relatedNodeId(paper, `cited:${index}`);
    if (seenIds.has(id)) return;
    seenIds.add(id);
    nodes.push(toGraphNode(paper, id, CITED_BY_KIND));
    links.push({ source: id, target: seedId });
  });

  cappedReferences.forEach((paper, index) => {
    const id = relatedNodeId(paper, `ref:${index}`);
    if (seenIds.has(id)) return;
    seenIds.add(id);
    nodes.push(toGraphNode(paper, id, REFERENCE_KIND));
    links.push({ source: seedId, target: id });
  });

  return { nodes, links };
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
): GraphNode {
  return {
    id,
    kind,
    title: paper.title,
    authors: paper.authors,
    year: paper.year,
    citationCount: paper.citation_count,
    url: paper.source_url,
  };
}

function nodeRadius(node: GraphNode): number {
  if (node.kind === SEED_KIND) return 16;
  const citations = node.citationCount ?? 0;
  return 4 + Math.log10(Math.max(citations, 1) + 1) * 4;
}

function nodeColor(node: GraphNode, graphData: GraphData): string {
  if (node.kind === SEED_KIND) return "#35824B";
  const yearRange = computeYearRange(graphData);
  const intensity = yearIntensity(node.year, yearRange);
  if (node.kind === CITED_BY_KIND) {
    return blendOver("#F59E0B", intensity);
  }
  return blendOver("#7BAD8A", intensity);
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
  if (min === max) {
    return { min: min - 1, max: max };
  }
  return { min, max };
}

function yearIntensity(year: number | null, range: { min: number; max: number }): number {
  if (year == null) return 0.4;
  const span = range.max - range.min;
  if (span <= 0) return 0.7;
  return Math.min(1, Math.max(0.25, (year - range.min) / span));
}

function blendOver(baseHex: string, intensity: number): string {
  const { r, g, b } = hexToRgb(baseHex);
  const alpha = 0.35 + intensity * 0.65;
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
