import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  WriterShortcutsModal,
  type WriterShortcutOverlayHandle,
  useWriterShortcuts,
} from "./useWriterShortcuts";

function setPlatform(value: string) {
  Object.defineProperty(window.navigator, "platform", {
    configurable: true,
    value,
  });
}

function ShortcutHarness({ initialMode = "closed" }: { initialMode?: string }) {
  const [mode, setMode] = useState(initialMode);
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const overlayRef = useRef<WriterShortcutOverlayHandle | null>(null);
  overlayRef.current = {
    openSelection: vi.fn(() => {
      setMode("edit");
      return true;
    }),
    openInsertion: vi.fn(() => {
      setMode("insert");
      return true;
    }),
    acceptPreview: vi.fn(() => {
      if (modeRef.current !== "preview") return false;
      setMode("applied");
      return true;
    }),
    rejectOrClose: vi.fn(() => {
      if (modeRef.current === "closed") return false;
      setMode("closed");
      return true;
    }),
    isOpen: () => modeRef.current !== "closed",
    hasPreview: () => modeRef.current === "preview",
  };

  const shortcuts = useWriterShortcuts({ overlayRef });

  return (
    <>
      <div data-testid="overlay-mode">{mode}</div>
      {shortcuts.showCheatsheet && (
        <WriterShortcutsModal
          modifierLabel={shortcuts.modifierLabel}
          onClose={() => shortcuts.setShowCheatsheet(false)}
        />
      )}
    </>
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("useWriterShortcuts", () => {
  it("opens the edit overlay from Cmd+E when a selection is present", () => {
    setPlatform("MacIntel");
    render(<ShortcutHarness />);

    fireEvent.keyDown(document, { key: "e", metaKey: true });

    expect(screen.getByTestId("overlay-mode").textContent).toBe("edit");
  });

  it("closes the overlay on Escape", () => {
    setPlatform("MacIntel");
    render(<ShortcutHarness initialMode="edit" />);

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.getByTestId("overlay-mode").textContent).toBe("closed");
  });

  it("renders the shortcuts cheatsheet from Shift+?", () => {
    setPlatform("MacIntel");
    render(<ShortcutHarness />);

    fireEvent.keyDown(document, { key: "?", shiftKey: true });

    expect(screen.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeTruthy();
    expect(screen.getByText("Cmd+E")).toBeTruthy();
    expect(screen.getByText("Cmd+Shift+E")).toBeTruthy();
    expect(screen.getByText("Cmd+Enter")).toBeTruthy();
    expect(screen.getByText("Escape")).toBeTruthy();
    expect(screen.getByText("Shift+?")).toBeTruthy();
  });
});
