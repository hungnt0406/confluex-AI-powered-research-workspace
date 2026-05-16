"use client";

import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import {
  ApiError,
  ChatMessage,
  ChatPatchStatus,
  ChatSectionPatch,
  WriterSectionRead,
  acceptWriterChatPatch,
  createWriterChat,
  getWriterChat,
  isInsufficientCreditsError,
  rejectWriterChatPatch,
  sendWriterChatMessage,
  undoWriterChatPatch,
} from "@/lib/api";

const PANEL_KEY_PREFIX = "writer-chat-panel:";
const CHAT_ID_KEY_PREFIX = "writer-chat-id:";
const PANEL_MIN_WIDTH = 360;
const PANEL_MAX_WIDTH = 720;
const PANEL_MIN_HEIGHT = 240;
const PANEL_MAX_HEIGHT = 900;
const PANEL_DEFAULT_HEIGHT = 380;
const PANEL_DEFAULT_WIDTH = 520;

interface PanelState {
  x: number;
  y: number;
  width: number;
  height: number;
}

function defaultPanelState(): PanelState {
  return {
    x: 240,
    y: 140,
    width: PANEL_DEFAULT_WIDTH,
    height: PANEL_DEFAULT_HEIGHT,
  };
}

function loadPanelState(userId: string): PanelState {
  if (typeof window === "undefined") return defaultPanelState();
  try {
    const raw = window.localStorage.getItem(`${PANEL_KEY_PREFIX}${userId}`);
    if (!raw) return defaultPanelState();
    const parsed = JSON.parse(raw) as Partial<PanelState & { mode?: string; collapsed?: boolean }>;
    return {
      x: typeof parsed.x === "number" ? parsed.x : 240,
      y: typeof parsed.y === "number" ? parsed.y : 140,
      width: clampWidth(typeof parsed.width === "number" ? parsed.width : PANEL_DEFAULT_WIDTH),
      height: clampHeight(typeof parsed.height === "number" ? parsed.height : PANEL_DEFAULT_HEIGHT),
    };
  } catch {
    return defaultPanelState();
  }
}

function persistPanelState(userId: string, state: PanelState) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(`${PANEL_KEY_PREFIX}${userId}`, JSON.stringify(state));
  } catch {
    /* ignore quota errors */
  }
}

function clampWidth(width: number) {
  return Math.min(Math.max(width, PANEL_MIN_WIDTH), PANEL_MAX_WIDTH);
}

function clampHeight(height: number) {
  return Math.min(Math.max(height, PANEL_MIN_HEIGHT), PANEL_MAX_HEIGHT);
}

export interface ChatPatchStatusUpdate {
  messageId: string;
  patchIndex: number;
  status: ChatPatchStatus;
}

interface WriterChatPanelProps {
  documentId: string;
  userId: string;
  token: string;
  sections: WriterSectionRead[];
  onAfterPatchApplied: () => void | Promise<void>;
  onScrollToInlineDiff: (messageId: string, patchIndex: number) => void;
  onChatBusyChange?: (busy: boolean) => void;
  onPatchesAvailable: (
    chatId: string,
    messageId: string,
    patches: ChatSectionPatch[],
  ) => void;
  externalPatchStatusUpdates?: ChatPatchStatusUpdate[];
  open: boolean;
  onClose: () => void;
}

interface DragState {
  startX: number;
  startY: number;
  startPanelX: number;
  startPanelY: number;
}

interface ResizeState {
  startX: number;
  startY: number;
  startWidth: number;
  startHeight: number;
}

function patchKey(messageId: string, idx: number) {
  return `${messageId}:${idx}`;
}

function truncatePreview(text: string, max = 40): string {
  const trimmed = text.replace(/\s+/g, " ").trim();
  if (trimmed.length <= max) return trimmed;
  return `${trimmed.slice(0, max - 1)}…`;
}

interface PatchRowProps {
  patch: ChatSectionPatch;
  section: WriterSectionRead | undefined;
  busy: boolean;
  onJump: () => void;
  onUndo: () => void;
  onAccept: () => void;
  onReject: () => void;
}

function statusPill(status: ChatPatchStatus): { label: string; className: string } {
  switch (status) {
    case "pending":
      return {
        label: "in editor",
        className:
          "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200",
      };
    case "applied":
      return {
        label: "✓ accepted",
        className:
          "bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-200",
      };
    case "rejected":
      return {
        label: "✕ rejected",
        className:
          "bg-stone-200 text-stone-700 dark:bg-stone-700/50 dark:text-stone-300",
      };
    case "stale":
      return {
        label: "↻ stale",
        className:
          "bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-200",
      };
  }
}

function PatchRow({
  patch,
  section,
  busy,
  onJump,
  onUndo,
  onAccept,
  onReject,
}: PatchRowProps) {
  const sectionTitle = patch.section_title || section?.title || "Section";
  const pill = statusPill(patch.status);
  const fromPreview = patch.original_text ? truncatePreview(patch.original_text) : "";
  const toPreview = patch.new_text ? truncatePreview(patch.new_text) : "";

  return (
    <div className="group flex items-center gap-2 rounded-lg border border-outline/15 bg-surface-container-lowest px-2.5 py-1.5 text-[11px] hover:border-primary/30">
      <button
        type="button"
        onClick={onJump}
        className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
        title={patch.rationale || "Jump to inline diff"}
      >
        <span aria-hidden="true" className="text-primary">●</span>
        <span className="truncate font-semibold text-on-surface">{sectionTitle}</span>
        <span className="text-on-surface-variant">·</span>
        {fromPreview ? (
          <span className="truncate italic text-rose-700/80 dark:text-rose-300/80">
            “{fromPreview}”
          </span>
        ) : (
          <span className="truncate italic text-on-surface-variant">(insertion)</span>
        )}
        <span aria-hidden="true" className="text-on-surface-variant">→</span>
        <span className="truncate italic text-emerald-700/90 dark:text-emerald-300/90">
          “{toPreview}”
        </span>
      </button>
      <span
        className={`shrink-0 rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide ${pill.className}`}
      >
        {pill.label}
      </span>
      {patch.status === "pending" && (
        <div className="hidden shrink-0 items-center gap-1 group-hover:flex">
          <button
            type="button"
            onClick={onReject}
            disabled={busy}
            className="inline-flex h-5 items-center rounded-full border border-outline/20 bg-surface px-2 text-[10px] font-semibold text-on-surface hover:bg-primary/5 disabled:opacity-50"
            title="Reject (fallback when editor not visible)"
          >
            ✕
          </button>
          <button
            type="button"
            onClick={onAccept}
            disabled={busy}
            className="inline-flex h-5 items-center rounded-full bg-primary px-2 text-[10px] font-semibold text-white hover:opacity-90 disabled:opacity-50"
            title="Accept (fallback when editor not visible)"
          >
            ✓
          </button>
        </div>
      )}
      {patch.status === "applied" && (
        <button
          type="button"
          onClick={onUndo}
          disabled={busy}
          className="shrink-0 rounded-full border border-emerald-300/60 bg-white/60 px-2 py-0.5 text-[9px] font-semibold text-emerald-800 hover:bg-white disabled:opacity-50 dark:border-emerald-700/50 dark:bg-emerald-900/40 dark:text-emerald-100"
        >
          Undo
        </button>
      )}
    </div>
  );
}

export function WriterChatPanelImpl({
  documentId,
  userId,
  token,
  sections,
  onAfterPatchApplied,
  onScrollToInlineDiff,
  onChatBusyChange,
  onPatchesAvailable,
  externalPatchStatusUpdates,
  open,
  onClose,
}: WriterChatPanelProps) {
  const [panelState, setPanelState] = useState<PanelState>(() => defaultPanelState());
  const [hydrated, setHydrated] = useState(false);
  const [chatId, setChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [creditBanner, setCreditBanner] = useState(false);
  const [pendingPatchOps, setPendingPatchOps] = useState<Set<string>>(() => new Set());
  const [pendingChatApply, setPendingChatApply] = useState(false);

  const messageListRef = useRef<HTMLDivElement | null>(null);
  const dragStateRef = useRef<DragState | null>(null);
  const resizeStateRef = useRef<ResizeState | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const announcedPatchesRef = useRef<Set<string>>(new Set());

  // Hydrate panel state from localStorage after mount (avoids SSR mismatch).
  useEffect(() => {
    setPanelState(loadPanelState(userId));
    setHydrated(true);
  }, [userId]);

  // Persist panel state when it changes (after hydration).
  useEffect(() => {
    if (!hydrated) return;
    persistPanelState(userId, panelState);
  }, [hydrated, panelState, userId]);

  // Surface busy state to the parent so it can suspend auto-save.
  useEffect(() => {
    onChatBusyChange?.(pendingChatApply);
  }, [onChatBusyChange, pendingChatApply]);

  // Rehydrate existing chat from localStorage, or start blank.
  useEffect(() => {
    let cancelled = false;
    const key = `${CHAT_ID_KEY_PREFIX}${documentId}`;
    const storedChatId = typeof window === "undefined" ? null : window.localStorage.getItem(key);
    if (!storedChatId) {
      setChatId(null);
      setMessages([]);
      return () => {
        cancelled = true;
      };
    }
    getWriterChat(documentId, storedChatId, token)
      .then((chat) => {
        if (cancelled) return;
        setChatId(chat.id);
        setMessages(chat.messages);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          window.localStorage.removeItem(key);
          setChatId(null);
          setMessages([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [documentId, token]);

  // Whenever a new assistant message arrives with patches, forward them up
  // so the workspace can render the inline diff overlay.
  useEffect(() => {
    if (!chatId) return;
    for (const msg of messages) {
      if (msg.role !== "assistant") continue;
      if (announcedPatchesRef.current.has(msg.id)) continue;
      if (msg.patches.length === 0) {
        announcedPatchesRef.current.add(msg.id);
        continue;
      }
      onPatchesAvailable(chatId, msg.id, msg.patches);
      announcedPatchesRef.current.add(msg.id);
    }
  }, [chatId, messages, onPatchesAvailable]);

  // Mirror external status updates from the inline overlay into our local
  // message tree so the row pill stays in sync.
  useEffect(() => {
    if (!externalPatchStatusUpdates || externalPatchStatusUpdates.length === 0) return;
    setMessages((prev) =>
      prev.map((msg) => {
        const updates = externalPatchStatusUpdates.filter((u) => u.messageId === msg.id);
        if (updates.length === 0) return msg;
        return {
          ...msg,
          patches: msg.patches.map((p, idx) => {
            const u = updates.find((entry) => entry.patchIndex === idx);
            return u ? { ...p, status: u.status } : p;
          }),
        };
      }),
    );
  }, [externalPatchStatusUpdates]);

  // Scroll to latest message on update.
  useEffect(() => {
    const node = messageListRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [messages, isSending]);

  const sectionsById = useMemo(() => {
    const map = new Map<string, WriterSectionRead>();
    for (const s of sections) map.set(s.id, s);
    return map;
  }, [sections]);

  // ----- Drag handling -----
  const handlePointerMove = useCallback((event: PointerEvent) => {
    if (dragStateRef.current) {
      const { startX, startY, startPanelX, startPanelY } = dragStateRef.current;
      const nextX = startPanelX + (event.clientX - startX);
      const nextY = startPanelY + (event.clientY - startY);
      setPanelState((prev) => ({
        ...prev,
        x: Math.max(8, nextX),
        y: Math.max(8, nextY),
      }));
      return;
    }
    if (resizeStateRef.current) {
      const r = resizeStateRef.current;
      const dw = event.clientX - r.startX;
      const dh = event.clientY - r.startY;
      setPanelState((prev) => ({
        ...prev,
        width: clampWidth(r.startWidth + dw),
        height: clampHeight(r.startHeight + dh),
      }));
    }
  }, []);

  const handlePointerUp = useCallback(
    (event: PointerEvent) => {
      const target = event.target as Element | null;
      if (target && target instanceof Element) {
        try {
          target.releasePointerCapture(event.pointerId);
        } catch {
          /* ignore */
        }
      }
      dragStateRef.current = null;
      resizeStateRef.current = null;
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    },
    [handlePointerMove],
  );

  const beginDrag = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return;
      event.preventDefault();
      const target = event.currentTarget;
      try {
        target.setPointerCapture(event.pointerId);
      } catch {
        /* ignore */
      }
      dragStateRef.current = {
        startX: event.clientX,
        startY: event.clientY,
        startPanelX: panelState.x,
        startPanelY: panelState.y,
      };
      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", handlePointerUp);
    },
    [handlePointerMove, handlePointerUp, panelState.x, panelState.y],
  );

  const beginResize = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      const target = event.currentTarget;
      try {
        target.setPointerCapture(event.pointerId);
      } catch {
        /* ignore */
      }
      resizeStateRef.current = {
        startX: event.clientX,
        startY: event.clientY,
        startWidth: panelState.width,
        startHeight: panelState.height,
      };
      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", handlePointerUp);
    },
    [handlePointerMove, handlePointerUp, panelState.height, panelState.width],
  );

  // ----- Chat helpers -----
  const updatePatchStatus = useCallback(
    (messageId: string, patchIndex: number, nextStatus: ChatSectionPatch["status"]) => {
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id !== messageId) return msg;
          return {
            ...msg,
            patches: msg.patches.map((p, idx) =>
              idx === patchIndex ? { ...p, status: nextStatus } : p,
            ),
          };
        }),
      );
    },
    [],
  );

  const markPatchOp = useCallback((key: string, busy: boolean) => {
    setPendingPatchOps((prev) => {
      const next = new Set(prev);
      if (busy) next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);

  const sendMessage = useCallback(async () => {
    const text = draft.trim();
    if (!text || isSending) return;
    setErrorMessage(null);
    setCreditBanner(false);
    setIsSending(true);
    try {
      let activeChatId = chatId;
      if (!activeChatId) {
        const created = await createWriterChat(documentId, token);
        activeChatId = created.id;
        setChatId(activeChatId);
        if (typeof window !== "undefined") {
          window.localStorage.setItem(`${CHAT_ID_KEY_PREFIX}${documentId}`, activeChatId);
        }
      }
      const turn = await sendWriterChatMessage(documentId, activeChatId, text, token);
      setMessages((prev) => [...prev, turn.user_message, turn.assistant_message]);
      setDraft("");
    } catch (err) {
      if (isInsufficientCreditsError(err)) {
        setCreditBanner(true);
      } else {
        setErrorMessage(err instanceof Error ? err.message : "Failed to send message.");
      }
    } finally {
      setIsSending(false);
    }
  }, [chatId, documentId, draft, isSending, token]);

  // Fallback Accept / Reject path used by the row buttons when the editor
  // isn't visible (e.g. prose mode). The inline diff overlay handles the
  // primary path.
  const acceptPatch = useCallback(
    async (messageId: string, patchIndex: number) => {
      if (!chatId) return;
      const key = patchKey(messageId, patchIndex);
      markPatchOp(key, true);
      setPendingChatApply(true);
      try {
        await acceptWriterChatPatch(documentId, chatId, messageId, patchIndex, token);
        updatePatchStatus(messageId, patchIndex, "applied");
        await onAfterPatchApplied();
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          updatePatchStatus(messageId, patchIndex, "stale");
        } else if (isInsufficientCreditsError(err)) {
          setCreditBanner(true);
        } else {
          setErrorMessage(err instanceof Error ? err.message : "Accept failed.");
        }
      } finally {
        markPatchOp(key, false);
        setPendingChatApply(false);
      }
    },
    [chatId, documentId, markPatchOp, onAfterPatchApplied, token, updatePatchStatus],
  );

  const rejectPatch = useCallback(
    async (messageId: string, patchIndex: number) => {
      if (!chatId) return;
      const key = patchKey(messageId, patchIndex);
      markPatchOp(key, true);
      try {
        await rejectWriterChatPatch(documentId, chatId, messageId, patchIndex, token);
        updatePatchStatus(messageId, patchIndex, "rejected");
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : "Reject failed.");
      } finally {
        markPatchOp(key, false);
      }
    },
    [chatId, documentId, markPatchOp, token, updatePatchStatus],
  );

  const undoPatch = useCallback(
    async (messageId: string, patchIndex: number) => {
      if (!chatId) return;
      const key = patchKey(messageId, patchIndex);
      markPatchOp(key, true);
      setPendingChatApply(true);
      try {
        await undoWriterChatPatch(documentId, chatId, messageId, patchIndex, token);
        updatePatchStatus(messageId, patchIndex, "pending");
        await onAfterPatchApplied();
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : "Undo failed.");
      } finally {
        markPatchOp(key, false);
        setPendingChatApply(false);
      }
    },
    [chatId, documentId, markPatchOp, onAfterPatchApplied, token, updatePatchStatus],
  );

  // Auto-grow textarea (capped at ~6 rows).
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "0px";
    const next = Math.min(ta.scrollHeight, 160);
    ta.style.height = `${next}px`;
  }, [draft]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        void sendMessage();
      }
    },
    [sendMessage],
  );

  if (!hydrated || !open) return null;

  const containerStyle: React.CSSProperties = {
    left: panelState.x,
    top: panelState.y,
    width: panelState.width,
    height: panelState.height,
  };

  return (
    <div
      role="dialog"
      aria-label="Writer document chat"
      className="fixed z-40 flex flex-col overflow-hidden rounded-2xl border border-outline/20 bg-surface shadow-2xl"
      style={containerStyle}
    >
      {/* Header / drag handle */}
      <div
        onPointerDown={beginDrag}
        className="flex h-11 shrink-0 cursor-move items-center gap-2.5 border-b border-outline/10 bg-surface px-4"
      >
        <svg viewBox="0 0 62 60" width="16" height="16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" className="shrink-0 text-primary">
          <path d="M 4,50 C 8,35 18,15 32,6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
          <path d="M 9,52 C 13,36 24,16 39,7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
          <path d="M 14,53 C 19,37 30,17 45,8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
          <path d="M 19,54 C 25,38 36,18 51,9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
          <path d="M 24,55 C 30,39 42,19 56,10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
          <path d="M 29,55 C 36,40 47,21 58,14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
          <path d="M 33,54 C 40,41 51,24 58,20" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
          <path d="M 37,53 C 43,42 53,27 57,26" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
          <path d="M 40,52 C 45,43 53,31 56,32" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
        </svg>
        <span className="text-sm font-semibold text-on-surface">Document chat</span>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={onClose}
            aria-label="Close chat panel"
            className="flex h-7 w-7 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-outline/15 hover:text-on-surface"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "16px" }} aria-hidden="true">close</span>
          </button>
        </div>
      </div>

      {/* Message list */}
      <div
        ref={messageListRef}
        className="custom-scrollbar flex-1 space-y-3 overflow-y-auto px-4 py-4"
      >
        {messages.length === 0 && (
          <div className="flex flex-col items-center gap-4 pt-6 pb-2">
            <div className="flex flex-col items-center gap-2 text-center">
              <svg viewBox="0 0 62 60" width="32" height="32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" className="text-primary/40">
                <path d="M 4,50 C 8,35 18,15 32,6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                <path d="M 9,52 C 13,36 24,16 39,7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                <path d="M 14,53 C 19,37 30,17 45,8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                <path d="M 19,54 C 25,38 36,18 51,9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                <path d="M 24,55 C 30,39 42,19 56,10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                <path d="M 29,55 C 36,40 47,21 58,14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                <path d="M 33,54 C 40,41 51,24 58,20" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                <path d="M 37,53 C 43,42 53,27 57,26" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                <path d="M 40,52 C 45,43 53,31 56,32" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
              <p className="text-xs font-medium text-on-surface">Ask for document-wide changes</p>
              <p className="text-[11px] text-on-surface-variant">Changes apply across one or more sections at once.</p>
            </div>
            <div className="flex flex-wrap justify-center gap-1.5">
              {["Tighten Related Work", "Reconcile abstract & conclusion", "Improve flow across sections"].map((hint) => (
                <button
                  key={hint}
                  type="button"
                  onClick={() => setDraft(hint)}
                  className="rounded-full border border-outline/20 bg-surface-container-lowest px-3 py-1 text-[11px] text-on-surface-variant transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary"
                >
                  {hint}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message) => {
          if (message.role === "user") {
            return (
              <div key={message.id} className="flex justify-end">
                <div className="max-w-[75%] whitespace-pre-wrap break-words rounded-2xl rounded-br-sm bg-primary/10 px-3 py-2 text-xs text-on-surface">
                  {message.content}
                </div>
              </div>
            );
          }

          const pendingCount = message.patches.filter((p) => p.status === "pending").length;

          return (
            <div key={message.id} className="flex flex-col gap-2">
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-outline/20 bg-surface-container-lowest px-3 py-2 text-xs text-on-surface">
                  <p className="whitespace-pre-wrap break-words">{message.content}</p>
                  {message.patches.length > 0 && (
                    <p
                      className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200"
                      title="edits ready in editor"
                    >
                      <span aria-hidden="true">✦</span>
                      {pendingCount > 0 ? (
                        <span>
                          {pendingCount === 1
                            ? "1 edit ready in editor"
                            : `${pendingCount} edits ready in editor`}
                        </span>
                      ) : (
                        <span>
                          {message.patches.length} edit
                          {message.patches.length === 1 ? "" : "s"}
                        </span>
                      )}
                    </p>
                  )}
                </div>
              </div>

              {message.patches.length > 0 && (
                <div className="ml-1 space-y-1.5">
                  {message.patches.map((patch, idx) => {
                    const opKey = patchKey(message.id, idx);
                    const busy = pendingPatchOps.has(opKey);
                    return (
                      <PatchRow
                        key={`${message.id}:${idx}`}
                        patch={patch}
                        section={sectionsById.get(patch.section_id)}
                        busy={busy}
                        onJump={() => onScrollToInlineDiff(message.id, idx)}
                        onUndo={() => void undoPatch(message.id, idx)}
                        onAccept={() => void acceptPatch(message.id, idx)}
                        onReject={() => void rejectPatch(message.id, idx)}
                      />
                    );
                  })}

                </div>
              )}
            </div>
          );
        })}

        {isSending && (
          <div className="flex justify-start">
            <div className="max-w-[60%] rounded-2xl rounded-bl-sm border border-outline/20 bg-surface-container-lowest px-3 py-2 text-xs text-on-surface-variant">
              <span className="inline-flex items-center gap-2">
                <span className="material-symbols-outlined animate-spin" style={{ fontSize: "14px" }} aria-hidden="true">
                  progress_activity
                </span>
                Thinking…
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Error / credit banners */}
      {creditBanner && (
        <div className="border-t border-rose-200/60 bg-rose-50 px-3 py-2 text-[11px] text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/30 dark:text-rose-200">
          Not enough credits — top up to keep chatting.{" "}
          <Link href="/billing" className="font-semibold underline">
            Top up
          </Link>
        </div>
      )}
      {errorMessage && !creditBanner && (
        <div className="flex items-center justify-between gap-2 border-t border-rose-200/60 bg-rose-50 px-3 py-2 text-[11px] text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/30 dark:text-rose-200">
          <span className="truncate">{errorMessage}</span>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="font-semibold text-rose-600 hover:text-rose-800"
            aria-label="Dismiss error"
          >
            ✕
          </button>
        </div>
      )}

      {/* Input */}
      <div className="shrink-0 border-t border-outline/10 bg-surface px-3 pb-3 pt-2.5">
        <div className="flex items-end gap-0 rounded-xl border border-outline/20 bg-surface-container-lowest focus-within:border-primary/40 transition-colors">
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask for document-wide changes…"
            rows={1}
            disabled={isSending}
            className="min-h-[38px] flex-1 resize-none bg-transparent px-3 py-2.5 text-xs text-on-surface outline-none placeholder:text-on-surface-variant/50 disabled:opacity-60"
          />
          <button
            type="button"
            onClick={() => void sendMessage()}
            disabled={isSending || !draft.trim()}
            className="mb-1.5 mr-1.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary text-white transition-all hover:opacity-90 disabled:opacity-30"
            aria-label="Send"
          >
            {isSending ? (
              <span className="material-symbols-outlined animate-spin" style={{ fontSize: "14px" }} aria-hidden="true">
                progress_activity
              </span>
            ) : (
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }} aria-hidden="true">arrow_upward</span>
            )}
          </button>
        </div>
        <p className="mt-1.5 px-1 text-[10px] text-on-surface-variant/50">
          3 credits per turn · Enter to send · Shift+Enter for newline
        </p>
      </div>

      {/* Corner resize handle */}
      <div
        onPointerDown={beginResize}
        aria-label="Resize chat panel"
        className="absolute bottom-1 right-1 h-3 w-3 cursor-nwse-resize rounded-sm bg-outline/30 hover:bg-outline/60"
      />
    </div>
  );
}

export const WriterChatPanel = memo(WriterChatPanelImpl);
WriterChatPanel.displayName = "WriterChatPanel";
export default WriterChatPanel;
