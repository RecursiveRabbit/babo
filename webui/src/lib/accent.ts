/** The accent colour: buttons that do the main thing on a page, the selected tab, focus rings, what needs you.
 *  A per-browser preference beside light and dark (Settings › Appearance). */
import { useCallback, useState } from "react";

export const ACCENTS = ["neutral", "blue", "green", "amber", "rose", "violet"] as const;
export type Accent = (typeof ACCENTS)[number];
const STORAGE_KEY = "babo-webui.accent";

export function readAccent(): Accent {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return (ACCENTS as readonly string[]).includes(value ?? "") ? value as Accent : "neutral";
  } catch {
    return "neutral";
  }
}

export function applyAccent(accent: Accent): void {
  const root = document.documentElement;
  if (accent === "neutral") delete root.dataset.accent;
  else root.dataset.accent = accent;
}

/** Apply the stored accent before the first paint. */
export function initializeAccent(): void {
  applyAccent(readAccent());
}

export function useAccent(): [Accent, (accent: Accent) => void] {
  const [accent, setState] = useState<Accent>(readAccent);
  const set = useCallback((value: Accent) => {
    setState(value);
    applyAccent(value);
    try { localStorage.setItem(STORAGE_KEY, value); } catch { /* browser-only preference */ }
  }, []);
  return [accent, set];
}
