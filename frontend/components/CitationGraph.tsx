"use client";

import dynamic from "next/dynamic";
// @ts-expect-error d3-force-3d is provided by react-force-graph but ships no local types.
import { forceCollide } from "d3-force-3d";
import {
  ChangeEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useChat } from "@/components/ChatProvider";
import {
  ApiError,
  CitationGraph as CitationGraphPayload,
  CitationGraphPaper,
  ProjectPaper,
} from "@/lib/api";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => null,
});

const SEED_KIND = "seed" as const;
const REFERENCE_KIND = "reference" as const;
const CITED_BY_KIND = "cited_by" as const;

type GraphNodeKind = typeof SEED_KIND | typeof REFERENCE_KIND | typeof CITED_BY_KIND;
type ViewMode = "graph" | "list";

type GraphNode = {
  id: string;
  kind: GraphNodeKind;
  title: string;
  authors: string[];
  year: number | null;
  abstract: string | null;
  citationCount: number | null;
  url: string | null;
  doi: string | null;
  source: string;
  sourcePaperId: string | null;
  pdfUrl: string | null;
  paper: CitationGraphPaper | null;
  inProject: boolean;
  projectPaperId: string | null;
  weight: number;
};

type GraphLink = {
  source: string;
  target: string;
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
  | { kind: "loading"; message: string }
  | { kind: "error"; message: string; status: number | null }
  | { kind: "loaded"; data: CitationGraphPayload };

const SEED_LIMIT = 20;
const PREFETCH_LIMIT = 3;
const MAX_CITED_BY = 10;
const MAX_REFERENCES = 20;

const SEED_RADIUS = 18;
const MIN_NODE_RADIUS = 5;
const MAX_NODE_RADIUS = 14;
const LINK_DIST_FAR = 160;
const LINK_DIST_NEAR = 60;
const SEED_STROKE = "#35824B";
const SEED_FILL = "#3daa5c";
const REF_HUE_START = "#4A7C59";
const CITE_HUE_START = "#D97706";
const PROJECT_NODE_STROKE = "#FFFFFF";

export default function CitationGraph({ projectId, papers }: CitationGraphProps) {
  const {
    citationGraphCache,
    getCitationGraph,
    prefetchCitationGraphs,
    addCitationGraphPaperToProject,
  } = useChat();
  const [seedPaperId, setSeedPaperId] = useState<string>(() => firstResolvablePaperId(papers));
  const [loadState, setLoadState] = useState<LoadState>({ kind: "idle" });
  const [viewMode, setViewMode] = useState<ViewMode>("graph");
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [importingNodeId, setImportingNodeId] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });
  const requestIdRef = useRef(0);
  const graphRef = useRef<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any

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
      setContainerSize({
        width: Math.floor(entry.contentRect.width),
        height: Math.floor(entry.contentRect.height),
      });
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const loadGraph = useCallback(
    async (options?: { force?: boolean }) => {
      if (!projectId || !seedPaper || !seedIsResolvable) return;
      const requestId = ++requestIdRef.current;
      const cacheKey = citationGraphCacheKey(projectId, seedPaper.id, SEED_LIMIT);
      const cachedPayload = !options?.force ? citationGraphCache[cacheKey] : undefined;
      if (cachedPayload) {
        setLoadState({ kind: "loaded", data: cachedPayload });
        return;
      }

      setSelectedNode(null);
      setImportError(null);
      setLoadState({ kind: "loading", message: "Resolving seed paper..." });
      const stageTimer = window.setTimeout(() => {
        if (requestId === requestIdRef.current) {
          setLoadState({ kind: "loading", message: "Fetching citation neighborhood..." });
        }
      }, 350);
      try {
        const payload = await getCitationGraph(projectId, seedPaper.id, {
          limit: SEED_LIMIT,
          force: options?.force,
        });
        window.clearTimeout(stageTimer);
        if (requestId !== requestIdRef.current) return;
        setLoadState({ kind: "loading", message: "Preparing graph layout..." });
        window.setTimeout(() => {
          if (requestId === requestIdRef.current) {
            setLoadState({ kind: "loaded", data: payload });
          }
        }, 150);
      } catch (err) {
        window.clearTimeout(stageTimer);
        if (requestId !== requestIdRef.current) return;
        const apiError = err instanceof ApiError ? err : null;
        setLoadState({
          kind: "error",
          message: err instanceof Error ? err.message : "Failed to load citation graph.",
          status: apiError?.status ?? null,
        });
      }
    },
    [citationGraphCache, getCitationGraph, projectId, seedIsResolvable, seedPaper],
  );

  useEffect(() => {
    if (!seedPaper) {
      setLoadState({ kind: "idle" });
      setSelectedNode(null);
      return;
    }
    if (!seedIsResolvable) {
      setLoadState({
        kind: "error",
        message:
          "This paper has no Semantic Scholar id, arXiv id, or DOI, so a citation graph cannot be resolved.",
        status: 400,
      });
      setSelectedNode(null);
      return;
    }
    void loadGraph();
  }, [loadGraph, seedIsResolvable, seedPaper]);

  useEffect(() => {
    if (!projectId || loadState.kind !== "loaded") return;
    const prefetchPaperIds = papers
      .filter((paper) => paper.id !== seedPaperId && isResolvablePaper(paper))
      .slice(0, PREFETCH_LIMIT)
      .map((paper) => paper.id);
    if (prefetchPaperIds.length > 0) {
      void prefetchCitationGraphs(projectId, prefetchPaperIds, { limit: SEED_LIMIT });
    }
  }, [loadState.kind, papers, prefetchCitationGraphs, projectId, seedPaperId]);

  const graphData = useMemo<GraphData | null>(() => {
    if (loadState.kind !== "loaded" || !seedPaper) return null;
    return buildGraphData(seedPaper, loadState.data, papers);
  }, [loadState, papers, seedPaper]);

  useEffect(() => {
    if (!selectedNode || !graphData) return;
    const updatedNode = graphData.nodes.find((node) => node.id === selectedNode.id);
    setSelectedNode(updatedNode ?? null);
  }, [graphData, selectedNode]);

  useEffect(() => {
    if (!graphData || !graphRef.current || viewMode !== "graph") return;
    const forceTimer = window.setTimeout(() => {
      const fg = graphRef.current;
      if (!fg) return;

      fg.d3Force("link")
        ?.distance((link: GraphLink) => {
          const strength = link.strength ?? 0.5;
          return LINK_DIST_FAR - strength * (LINK_DIST_FAR - LINK_DIST_NEAR);
        })
        .strength((link: GraphLink) => 0.3 + (link.strength ?? 0.5) * 0.5);
      fg.d3Force("charge")?.strength(-450);
      fg.d3Force(
        "collide",
        forceCollide((node: GraphNode) => nodeRadius(node) + 10).iterations(2),
      );
      fg.d3ReheatSimulation();
    }, 50);
    return () => window.clearTimeout(forceTimer);
  }, [graphData, viewMode]);

  const onSeedChange = useCallback((event: ChangeEvent<HTMLSelectElement>) => {
    setSeedPaperId(event.target.value);
  }, []);

  const onNodeClick = useCallback((rawNode: object) => {
    setSelectedNode(rawNode as GraphNode);
    setImportError(null);
  }, []);

  const importSelectedNode = useCallback(
    async (node: GraphNode) => {
      if (!projectId || !node.paper || node.inProject) return;
      setImportingNodeId(node.id);
      setImportError(null);
      try {
        await addCitationGraphPaperToProject(projectId, node.paper);
      } catch (err) {
        setImportError(err instanceof Error ? err.message : "Failed to add this paper.");
      } finally {
        setImportingNodeId(null);
      }
    },
    [addCitationGraphPaperToProject, projectId],
  );

  const nodeCanvasObject = useCallback(
    (rawNode: object, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const node = rawNode as GraphNode & { x?: number; y?: number };
      if (node.x == null || node.y == null) return;
      const radius = nodeRadius(node);
      const fill = nodeFill(node, graphData);
      const { x, y } = node;

      ctx.save();

      if (node.kind === SEED_KIND) {
        const grd = ctx.createRadialGradient(x, y, radius * 0.6, x, y, radius * 2.2);
        grd.addColorStop(0, "rgba(53,170,92,0.16)");
        grd.addColorStop(1, "rgba(53,170,92,0)");
        ctx.beginPath();
        ctx.arc(x, y, radius * 2.2, 0, Math.PI * 2);
        ctx.fillStyle = grd;
        ctx.fill();
      }

      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = fill;
      ctx.fill();

      const isSelected = selectedNode?.id === node.id;
      ctx.strokeStyle =
        node.kind === SEED_KIND ? SEED_STROKE : node.inProject ? PROJECT_NODE_STROKE : "rgba(255,255,255,0.18)";
      ctx.lineWidth = (node.kind === SEED_KIND || node.inProject || isSelected ? 2.5 : 1) / globalScale;
      ctx.stroke();

      if (node.inProject && node.kind !== SEED_KIND) {
        ctx.beginPath();
        ctx.arc(x + radius * 0.65, y - radius * 0.65, Math.max(3, 5 / globalScale), 0, Math.PI * 2);
        ctx.fillStyle = "#ffffff";
        ctx.fill();
        ctx.fillStyle = "#35824B";
        ctx.font = `${Math.max(8 / globalScale, 3)}px Inter, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("✓", x + radius * 0.65, y - radius * 0.65);
      }

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
        const textWidth = ctx.measureText(label).width;
        const pad = fontSize * 0.4;
        const pillH = fontSize + pad * 2;
        const pillY = y + radius + pillH * 0.6;
        ctx.fillStyle = "rgba(255,255,255,0.86)";
        ctx.beginPath();
        ctx.roundRect?.(x - textWidth / 2 - pad, pillY - pillH / 2, textWidth + pad * 2, pillH, pillH / 2);
        ctx.fill();
        ctx.strokeStyle = "rgba(148,163,184,0.28)";
        ctx.lineWidth = 1 / globalScale;
        ctx.stroke();
        ctx.fillStyle = "#1E293B";
        ctx.fillText(label, x, pillY);
      }

      ctx.restore();
    },
    [graphData, selectedNode],
  );

  const linkCanvasObject = useCallback((rawLink: object, ctx: CanvasRenderingContext2D) => {
    const link = rawLink as GraphLink & {
      source: GraphNode & { x?: number; y?: number };
      target: GraphNode & { x?: number; y?: number };
    };
    const { source, target } = link;
    if (source.x == null || source.y == null || target.x == null || target.y == null) return;
    const strength = link.strength ?? 0.5;
    const opacity = 0.12 + strength * 0.35;
    const width = 0.5 + strength * 2;
    const baseColor = `rgba(100, 116, 139, ${Math.min(0.55, opacity + 0.12).toFixed(2)})`;

    ctx.save();
    ctx.beginPath();
    ctx.moveTo(source.x, source.y);
    ctx.lineTo(target.x, target.y);
    ctx.strokeStyle = baseColor;
    ctx.lineWidth = width;
    ctx.stroke();
    ctx.restore();
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
                {!isResolvablePaper(paper) ? " - no DOI/arXiv id" : ""}
              </option>
            ))
          )}
        </select>
      </div>

      <div className="flex items-center justify-between gap-2">
        <div className="inline-flex rounded-lg bg-surface-container-low p-0.5">
          <ViewModeButton label="Graph" icon="hub" active={viewMode === "graph"} onClick={() => setViewMode("graph")} />
          <ViewModeButton label="List" icon="list_alt" active={viewMode === "list"} onClick={() => setViewMode("list")} />
        </div>
        {loadState.kind === "loaded" && graphData && (
          <span className="text-[10px] text-hint">{graphData.nodes.length - 1} related papers</span>
        )}
      </div>

      <div
        ref={containerRef}
        className="relative flex-1 min-h-[320px] overflow-hidden rounded-xl border border-outline/20 bg-surface-container-lowest shadow-sm"
      >
        {loadState.kind === "loading" && (
          <CenterMessage>
            <div className="flex items-center gap-2 text-[11px] text-hint">
              <span className="material-symbols-outlined animate-spin text-base">progress_activity</span>
              {loadState.message}
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
                  onClick={() => void loadGraph({ force: true })}
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
        {loadState.kind === "loaded" && graphData && viewMode === "graph" && containerSize.width > 0 && (
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            width={containerSize.width}
            height={containerSize.height}
            backgroundColor="rgba(0,0,0,0)"
            nodeCanvasObject={nodeCanvasObject}
            nodeCanvasObjectMode={() => "replace"}
            linkCanvasObject={linkCanvasObject}
            linkCanvasObjectMode={() => "replace"}
            nodePointerAreaPaint={(rawNode, color, ctx) => {
              const node = rawNode as GraphNode & { x?: number; y?: number };
              if (node.x == null || node.y == null) return;
              const r = nodeRadius(node) + 8;
              ctx.beginPath();
              ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
              ctx.fillStyle = color;
              ctx.fill();
            }}
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.35}
            cooldownTicks={180}
            warmupTicks={30}
            onNodeClick={onNodeClick}
            onEngineStop={() => graphRef.current?.zoomToFit?.(400, 40)}
            nodeLabel={(rawNode: object) => buildNodeTooltip(rawNode as GraphNode)}
          />
        )}
        {loadState.kind === "loaded" && graphData && viewMode === "list" && (
          <CitationGraphList graphData={graphData} onSelectNode={setSelectedNode} />
        )}
        {selectedNode && (
          <NodePreviewCard
            node={selectedNode}
            importing={importingNodeId === selectedNode.id}
            importError={importError}
            onClose={() => {
              setSelectedNode(null);
              setImportError(null);
            }}
            onImport={() => void importSelectedNode(selectedNode)}
          />
        )}
      </div>

      <Legend />
    </div>
  );
}

function CenterMessage({ children }: { children: React.ReactNode }) {
  return <div className="absolute inset-0 flex items-center justify-center px-4">{children}</div>;
}

function ViewModeButton({
  label,
  icon,
  active,
  onClick,
}: {
  label: string;
  icon: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-[10px] font-bold uppercase tracking-widest transition-colors ${
        active ? "bg-background text-on-surface shadow-sm" : "text-hint hover:text-on-surface"
      }`}
    >
      <span className="material-symbols-outlined" aria-hidden="true" style={{ fontSize: "14px" }}>
        {icon}
      </span>
      {label}
    </button>
  );
}

function NodePreviewCard({
  node,
  importing,
  importError,
  onClose,
  onImport,
}: {
  node: GraphNode;
  importing: boolean;
  importError: string | null;
  onClose: () => void;
  onImport: () => void;
}) {
  return (
    <div className="absolute left-3 right-3 top-3 z-20 rounded-lg border border-outline/30 bg-background/95 p-3 shadow-xl backdrop-blur">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-1.5">
            <span className="rounded-full bg-surface-container-low px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest text-hint">
              {nodeKindLabel(node.kind)}
            </span>
            {node.inProject && (
              <span className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest text-primary">
                <span className="material-symbols-outlined" aria-hidden="true" style={{ fontSize: "12px" }}>
                  check
                </span>
                In project
              </span>
            )}
          </div>
          <h4 className="line-clamp-3 text-[12px] font-semibold leading-snug text-on-surface">{node.title}</h4>
          <p className="mt-1 text-[10px] text-hint">
            {node.authors.slice(0, 3).join(", ") || "Unknown authors"}
            {node.authors.length > 3 ? ` +${node.authors.length - 3}` : ""}
            {node.year ? ` · ${node.year}` : ""}
            {node.citationCount != null ? ` · ${node.citationCount.toLocaleString()} citations` : ""}
          </p>
          <p className="mt-2 line-clamp-4 text-[10px] leading-relaxed text-on-surface-variant">
            {node.abstract || "No abstract snippet is available for this paper."}
          </p>
          {importError && <p className="mt-2 text-[10px] text-red-400">{importError}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {node.url && (
              <a
                href={node.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-7 items-center gap-1 rounded-md border border-outline/30 px-2 text-[10px] font-medium text-on-surface transition-colors hover:bg-surface-container-low"
              >
                <span className="material-symbols-outlined" aria-hidden="true" style={{ fontSize: "13px" }}>
                  open_in_new
                </span>
                Semantic Scholar
              </a>
            )}
            {node.paper && !node.inProject && (
              <button
                type="button"
                onClick={onImport}
                disabled={importing}
                className="inline-flex h-7 items-center gap-1 rounded-md bg-primary px-2 text-[10px] font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-60"
              >
                <span className="material-symbols-outlined" aria-hidden="true" style={{ fontSize: "13px" }}>
                  {importing ? "progress_activity" : "add"}
                </span>
                {importing ? "Adding..." : "Add to project"}
              </button>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close paper preview"
          className="inline-flex h-7 w-7 flex-none items-center justify-center rounded-md text-hint transition-colors hover:bg-surface-container-low hover:text-on-surface"
        >
          <span className="material-symbols-outlined" aria-hidden="true" style={{ fontSize: "16px" }}>
            close
          </span>
        </button>
      </div>
    </div>
  );
}

function CitationGraphList({
  graphData,
  onSelectNode,
}: {
  graphData: GraphData;
  onSelectNode: (node: GraphNode) => void;
}) {
  const seed = graphData.nodes.find((node) => node.kind === SEED_KIND);
  const references = graphData.nodes.filter((node) => node.kind === REFERENCE_KIND);
  const citedBy = graphData.nodes.filter((node) => node.kind === CITED_BY_KIND);

  return (
    <div className="h-full overflow-y-auto p-3 custom-scrollbar">
      {seed && <NodeListSection title="Seed Paper" nodes={[seed]} onSelectNode={onSelectNode} />}
      <NodeListSection title="References" nodes={references} onSelectNode={onSelectNode} />
      <NodeListSection title="Cited By" nodes={citedBy} onSelectNode={onSelectNode} />
    </div>
  );
}

function NodeListSection({
  title,
  nodes,
  onSelectNode,
}: {
  title: string;
  nodes: GraphNode[];
  onSelectNode: (node: GraphNode) => void;
}) {
  return (
    <section className="mb-4 last:mb-0">
      <h4 className="mb-2 text-[10px] font-bold uppercase tracking-widest text-hint">
        {title} ({nodes.length})
      </h4>
      {nodes.length === 0 ? (
        <p className="text-[10px] text-hint">No papers returned.</p>
      ) : (
        <ul className="space-y-2">
          {nodes.map((node) => (
            <li key={node.id}>
              <button
                type="button"
                onClick={() => onSelectNode(node)}
                className="w-full rounded-lg border border-outline/20 bg-background/70 p-2 text-left transition-colors hover:border-primary/30"
              >
                <span className="line-clamp-2 text-[11px] font-medium leading-snug text-on-surface">
                  {node.title}
                </span>
                <span className="mt-1 block truncate text-[10px] text-hint">
                  {node.authors.slice(0, 2).join(", ") || "Unknown authors"}
                  {node.year ? ` · ${node.year}` : ""}
                  {node.inProject ? " · In project" : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[10px] text-hint">
      <LegendDot label="Seed paper" color="#3daa5c" />
      <LegendDot label="References" color="#7BAD8A" />
      <LegendDot label="Cited by" color="#F59E0B" />
      <span className="inline-flex items-center gap-1">
        <span className="inline-flex h-2.5 w-2.5 items-center justify-center rounded-full border border-white text-[7px] text-white">✓</span>
        <span>In project</span>
      </span>
      <span className="ml-auto opacity-70">size = citation count · color brightness = recency</span>
    </div>
  );
}

function LegendDot({ label, color }: { label: string; color: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />
      <span>{label}</span>
    </span>
  );
}

function buildGraphData(
  seedPaper: ProjectPaper,
  payload: CitationGraphPayload,
  projectPapers: ProjectPaper[],
): GraphData {
  const seedId = `seed:${seedPaper.id}`;
  const cappedCitedBy = payload.cited_by.slice(0, MAX_CITED_BY);
  const cappedReferences = payload.references.slice(0, MAX_REFERENCES);
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
      abstract: seedPaper.abstract ?? null,
      citationCount: seedPaper.citation_count ?? payload.citation_count ?? null,
      url: seedPaper.source_url ?? null,
      doi: seedPaper.doi ?? null,
      source: seedPaper.source,
      sourcePaperId: seedPaper.source_paper_id ?? null,
      pdfUrl: seedPaper.pdf_url ?? null,
      paper: null,
      inProject: true,
      projectPaperId: seedPaper.id,
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
    nodes.push(toGraphNode(paper, id, CITED_BY_KIND, weight, projectPapers));
    links.push({ source: id, target: seedId, strength: weight });
  });

  cappedReferences.forEach((paper, index) => {
    const id = relatedNodeId(paper, `ref:${index}`);
    if (seenIds.has(id)) return;
    seenIds.add(id);
    const weight = normaliseWeight(paper.citation_count, maxCount);
    nodes.push(toGraphNode(paper, id, REFERENCE_KIND, weight, projectPapers));
    links.push({ source: seedId, target: id, strength: weight });
  });

  return { nodes, links };
}

function normaliseWeight(count: number | null | undefined, max: number): number {
  if (count == null || max <= 0) return 0.3;
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
  projectPapers: ProjectPaper[],
): GraphNode {
  const matchedPaper = findProjectPaperMatch(paper, projectPapers);
  return {
    id,
    kind,
    title: paper.title,
    authors: paper.authors,
    year: paper.year,
    abstract: paper.abstract,
    citationCount: paper.citation_count,
    url: paper.source_url,
    doi: paper.doi,
    source: paper.source,
    sourcePaperId: paper.source_paper_id,
    pdfUrl: paper.pdf_url,
    paper,
    inProject: matchedPaper != null,
    projectPaperId: matchedPaper?.id ?? null,
    weight,
  };
}

function findProjectPaperMatch(paper: CitationGraphPaper, projectPapers: ProjectPaper[]) {
  const source = paper.source.trim().toLowerCase();
  const sourcePaperId = paper.source_paper_id?.trim().toLowerCase() ?? null;
  const doi = paper.doi?.trim().toLowerCase() ?? null;
  const title = normalizeTitle(paper.title);
  return projectPapers.find((projectPaper) => {
    if (
      sourcePaperId &&
      projectPaper.source.trim().toLowerCase() === source &&
      projectPaper.source_paper_id?.trim().toLowerCase() === sourcePaperId
    ) {
      return true;
    }
    if (doi && projectPaper.doi?.trim().toLowerCase() === doi) return true;
    return normalizeTitle(projectPaper.title) === title;
  });
}

function nodeRadius(node: GraphNode): number {
  if (node.kind === SEED_KIND) return SEED_RADIUS;
  return MIN_NODE_RADIUS + node.weight * (MAX_NODE_RADIUS - MIN_NODE_RADIUS);
}

function nodeFill(node: GraphNode, graphData: GraphData | null): string {
  if (node.kind === SEED_KIND) return SEED_FILL;
  const yearRange = graphData ? computeYearRange(graphData) : { min: 2010, max: new Date().getFullYear() };
  const intensity = yearIntensity(node.year, yearRange);
  return blendOver(node.kind === CITED_BY_KIND ? CITE_HUE_START : REF_HUE_START, intensity);
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
  if (min === max) return { min: min - 1, max };
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

function buildNodeTooltip(node: GraphNode): string {
  const authorPreview = node.authors.slice(0, 2).join(", ");
  const moreAuthors = node.authors.length > 2 ? ` +${node.authors.length - 2}` : "";
  const yearLabel = node.year ? ` (${node.year})` : "";
  const citationLabel =
    node.citationCount != null ? ` · ${node.citationCount.toLocaleString()} citations` : "";
  const projectLabel = node.inProject ? "\nAlready in project" : "";
  return `${escapeHtml(node.title)}${yearLabel}\n${escapeHtml(authorPreview)}${moreAuthors}${citationLabel}${projectLabel}`;
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function nodeKindLabel(kind: GraphNodeKind): string {
  if (kind === SEED_KIND) return "Seed paper";
  if (kind === REFERENCE_KIND) return "Reference";
  return "Cited by";
}

function truncate(value: string, max: number): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

function normalizeTitle(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9\s]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
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

function citationGraphCacheKey(projectId: string, paperId: string, limit: number) {
  return `${projectId}:${paperId}:${limit}`;
}

function humanizeCitationError(message: string, status: number | null): string {
  if (status === 400) return message || "This paper can't be resolved exactly upstream.";
  if (status === 404) return "Semantic Scholar couldn't find an exact match for this paper.";
  if (status === 502) return "Semantic Scholar is unavailable right now. Please retry in a moment.";
  return message || "Failed to load citation graph.";
}
