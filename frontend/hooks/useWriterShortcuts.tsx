import {
  type RefObject,
  type KeyboardEvent as ReactKeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

export interface WriterShortcutOverlayHandle {
  openSelection: () => boolean;
  openInsertion: () => boolean;
  acceptPreview: () => boolean;
  rejectOrClose: () => boolean;
  isOpen: () => boolean;
  hasPreview: () => boolean;
}

interface UseWriterShortcutsArgs {
  overlayRef: RefObject<WriterShortcutOverlayHandle | null>;
  editorRootRef?: RefObject<HTMLElement | null>;
}

const SHORTCUTS = [
  { id: "edit", keys: "E", description: "Open edit overlay for the current selection" },
  { id: "insert", keys: "Shift+E", description: "Open insert overlay at the cursor" },
  { id: "apply", keys: "Enter", description: "Apply the shown preview" },
  { id: "close", keys: "Escape", description: "Reject or close the open overlay" },
  { id: "help", keys: "Shift+?", description: "Show keyboard shortcuts" },
] as const;

function isMacPlatform() {
  if (typeof navigator === "undefined") return false;
  return /Mac|iPhone|iPad|iPod/i.test(navigator.platform);
}

function isEditableElement(target: EventTarget | null) {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.tagName === "SELECT")
  );
}

function shouldSkipTarget(target: EventTarget | null, editorRoot: HTMLElement | null) {
  if (!(target instanceof HTMLElement)) return false;
  if (!isEditableElement(target)) return false;
  if (editorRoot?.contains(target)) return false;
  if (target.closest("[data-writer-editor-overlay='true']")) return false;
  return true;
}

function keyLabel(modifierLabel: string, keys: string) {
  if (keys === "Escape" || keys === "Shift+?") return keys;
  return `${modifierLabel}+${keys}`;
}

export function useWriterShortcuts({ overlayRef, editorRootRef }: UseWriterShortcutsArgs) {
  const [showCheatsheet, setShowCheatsheet] = useState(false);
  const modifierLabel = isMacPlatform() ? "Cmd" : "Ctrl";
  const bindings = useMemo(
    () =>
      SHORTCUTS.map((shortcut) => ({
        ...shortcut,
        label: keyLabel(modifierLabel, shortcut.keys),
      })),
    [modifierLabel],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (shouldSkipTarget(event.target, editorRootRef?.current ?? null)) return;

      const overlay = overlayRef.current;
      const primaryModifier = isMacPlatform() ? event.metaKey : event.ctrlKey;

      if (event.shiftKey && (event.key === "?" || event.key === "/")) {
        event.preventDefault();
        setShowCheatsheet(true);
        return;
      }

      if (event.key === "Escape" && overlay?.isOpen()) {
        if (overlay.rejectOrClose()) event.preventDefault();
        return;
      }

      if (!primaryModifier || event.altKey) return;

      if (event.key === "Enter" && overlay?.hasPreview()) {
        if (overlay.acceptPreview()) event.preventDefault();
        return;
      }

      if (event.key.toLowerCase() === "e" && event.shiftKey) {
        if (overlay?.openInsertion()) event.preventDefault();
        return;
      }

      if (event.key.toLowerCase() === "e" && !event.shiftKey) {
        if (overlay?.openSelection()) event.preventDefault();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [editorRootRef, overlayRef]);

  return {
    bindings,
    modifierLabel,
    showCheatsheet,
    setShowCheatsheet,
  };
}

export function WriterShortcutsModal({
  modifierLabel,
  onClose,
}: {
  modifierLabel: string;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  const bindings = SHORTCUTS.map((shortcut) => ({
    ...shortcut,
    label: keyLabel(modifierLabel, shortcut.keys),
  }));

  const closeModal = useCallback(() => {
    onClose();
  }, [onClose]);

  const handleKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeModal();
        return;
      }

      if (event.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          "a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex='-1'])",
        ),
      ).filter((element) => element.offsetParent !== null);
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
        return;
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    },
    [closeModal],
  );

  useEffect(() => {
    previouslyFocusedRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButtonRef.current?.focus();

    return () => {
      previouslyFocusedRef.current?.focus();
    };
  }, []);

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="writer-shortcuts-title"
        onKeyDown={handleKeyDown}
        className="w-[420px] max-w-[92vw] rounded-2xl border border-outline/20 bg-surface p-4 shadow-2xl"
      >
        <div className="flex items-center justify-between">
          <h2 id="writer-shortcuts-title" className="text-sm font-semibold text-on-surface">
            Keyboard shortcuts
          </h2>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={closeModal}
            aria-label="Close shortcuts"
            className="flex h-8 w-8 items-center justify-center rounded-full text-on-surface-variant hover:bg-primary/5"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "16px" }} aria-hidden="true">
              close
            </span>
          </button>
        </div>
        <div className="mt-3 space-y-2">
          {bindings.map((binding) => (
            <div
              key={binding.id}
              className="flex items-center justify-between gap-4 rounded-xl bg-surface-container-lowest px-3 py-2"
            >
              <span className="text-xs text-on-surface-variant">{binding.description}</span>
              <kbd className="shrink-0 rounded-md border border-outline/20 bg-background px-2 py-1 text-[11px] font-semibold text-on-surface">
                {binding.label}
              </kbd>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
