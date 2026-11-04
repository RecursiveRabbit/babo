import { useEffect, useState, useSyncExternalStore } from "react";
import { AlertCircle, CheckCircle2, Clock, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useClient } from "@/providers/ClientProvider";
import { fetchTownActivity, type TownActivity } from "@/lib/api";
import { cn } from "@/lib/utils";

const FAST_MS = 2_000; // while something is waiting or running
const SLOW_MS = 15_000;
const SHOW_DONE_MS = 120_000; // a finished entry stays beside its button this long (a failure until it's cleared)

/** One poller for the whole page: every ActivityLine reads the same list. */
let entries: TownActivity[] = [];
const listeners = new Set<() => void>();
let timer: number | undefined;
let tokenFor: (() => string) | null = null;

async function poll(): Promise<void> {
  if (!tokenFor) return;
  try {
    const got = (await fetchTownActivity(tokenFor())).activity;
    entries = Array.isArray(got) ? got : [];  // (an older Babo has no activity: show none)
    listeners.forEach((l) => l());
  } catch { /* the next poll tries again */ }
  schedule();
}

function schedule(): void {
  window.clearTimeout(timer);
  if (listeners.size === 0) return;
  timer = window.setTimeout(() => { if (document.visibilityState === "visible") void poll(); else schedule(); },
    entries.some((e) => e.active) ? FAST_MS : SLOW_MS);
}

/** Look again now (after a button that starts something), so its status shows at once. */
export function refreshActivity(): void { void poll(); }

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (listeners.size === 1) void poll();
  return () => { listeners.delete(listener); if (listeners.size === 0) window.clearTimeout(timer); };
}

function elapsed(from: string, now: number): string {
  const seconds = Math.max(0, Math.round((now - new Date(from).getTime()) / 1000));
  return seconds >= 60 ? `${Math.floor(seconds / 60)} min ${seconds % 60} s` : `${seconds} s`;
}

/** What one thing is doing, right where it was asked for: waiting, running (with how long), done, or failed and why. */
export function ActivityLine({ activityKey, className }: { activityKey: string; className?: string }) {
  const { t } = useTranslation();
  const { getToken } = useClient();
  tokenFor = getToken;
  const entry = useSyncExternalStore(subscribe, () => entries.find((e) => e.key === activityKey));
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!entry?.active) return;
    const tick = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(tick);
  }, [entry?.active]);
  if (!entry) return null;
  const finishedAgo = entry.finished ? now - new Date(entry.finished).getTime() : 0;
  if (entry.status === "done" && finishedAgo > SHOW_DONE_MS) return null;
  const Icon = entry.status === "running" ? Loader2 : entry.status === "waiting" ? Clock : entry.status === "done" ? CheckCircle2 : AlertCircle;
  const said = {
    waiting: t("town.activityWaiting", { defaultValue: "Waiting to start" }),
    running: t("town.activityRunning", { defaultValue: "Working on it · {{time}}", time: elapsed(entry.started, now) }),
    done: t("town.activityDone", { defaultValue: "Done" }),
    failed: t("town.activityFailed", { defaultValue: "Didn't go through" }),
  }[entry.status];
  return <div role="status" aria-live="polite" data-status={entry.status}
    className={cn("flex basis-full items-start gap-2 rounded-md px-2 py-1.5 text-xs animate-in fade-in-0 slide-in-from-top-1 duration-300 motion-reduce:animate-none",
      entry.status === "failed" ? "bg-destructive/10 text-destructive" : entry.status === "done" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
        : "bg-muted text-foreground", className)}>
    <Icon className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", entry.status === "running" && "animate-spin")} aria-hidden />
    <span className="min-w-0">
      <span className="font-medium">{said}</span>{": "}{entry.label}
      {entry.detail && <span className="text-muted-foreground"> · {entry.detail}</span>}
    </span>
  </div>;
}
