import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Clock, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SettingsGroup } from "@/components/settings/shared/SettingsControls";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useClient } from "@/providers/ClientProvider";
import { fetchTownLogs, fetchTownNow, type TownActivity, type TownLogs, type TownNow } from "@/lib/api";
import { cn } from "@/lib/utils";

const NOW_MS = 3_000;
const LOGS_MS = 5_000;

function ago(when: string): string {
  const seconds = Math.max(0, Math.round((Date.now() - new Date(when).getTime()) / 1000));
  return seconds >= 3600 ? `${Math.floor(seconds / 3600)} h` : seconds >= 60 ? `${Math.floor(seconds / 60)} min` : `${seconds} s`;
}

/** What Babo is doing right now, and its logs: the same as `babo now` and `babo logs`. */
export function ActivityView({ onError }: { onError: (message: string) => void }) {
  const { t } = useTranslation();
  return <>
    <p className="settings-list-inset text-[13px] leading-6 text-muted-foreground">
      {t("town.activityIntro", { defaultValue: "What's happening in the town right now, and what Babo's services have been saying. In the terminal: babo now, babo logs." })}
    </p>
    <RightNow onError={onError} />
    <Logs onError={onError} />
  </>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section aria-label={title}>
    <h2 className="settings-list-inset mt-2 text-[13px] font-medium text-muted-foreground">{title}</h2>
    <SettingsGroup>{children}</SettingsGroup>
  </section>;
}

function RightNow({ onError }: { onError: (message: string) => void }) {
  const { t } = useTranslation();
  const { getToken } = useClient();
  const [now, setNow] = useState<TownNow | null>(null);
  const load = useCallback(async () => {
    try { setNow(await fetchTownNow(getToken())); } catch (reason) { onError(reason instanceof Error ? reason.message : String(reason)); }
  }, [getToken, onError]);
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void load(); }, NOW_MS);
    return () => window.clearInterval(timer);
  }, [load]);
  if (!now) return <p className="settings-list-inset text-[13px] text-muted-foreground"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />{t("town.loading", { defaultValue: "Loading the town…" })}</p>;
  const q = now.queue;
  const running = now.activity.filter((a) => a.active);
  const finished = now.activity.filter((a) => !a.active);
  return <>
    <Section title={t("town.rightNow", { defaultValue: "Right now" })}>
      <Row label={t("town.modelQueue", { defaultValue: "Model" })}>
        {q.slots === undefined
          ? <span className="text-destructive">{t("town.queueDown", { defaultValue: "The model queue isn't answering." })}</span>
          : t("town.queueState", { defaultValue: "{{active}} of {{slots}} busy · {{waiting}} waiting", active: q.active ?? 0, slots: q.slots, waiting: q.waiting ?? 0 })}
      </Row>
      <Row label={t("town.upkeep", { defaultValue: "Upkeep" })}>
        {now.upkeep.running ? t("town.upkeepWorking", { defaultValue: "Working now." })
          : now.upkeep.waiting.length ? `${t("town.upkeepWaitingFor", { defaultValue: "Waiting" })}: ${now.upkeep.waiting.join(" · ")}`
            : t("town.upkeepIdle", { defaultValue: "Nothing is waiting." })}
      </Row>
      {running.length === 0 && now.sessions.length === 0 && now.errands.length === 0 &&
        <p className="settings-list-row py-3 text-[13px] text-muted-foreground">{t("town.allQuiet", { defaultValue: "All quiet: nothing is running." })}</p>}
      {running.map((a) => <ActivityRow key={a.key} entry={a} />)}
      {now.sessions.map((s) => <Row key={`${s.resident}/${s.id}`} label={s.resident}>
        <span className={cn(s.state === "waiting" && "font-medium text-amber-700 dark:text-amber-300")}>{s.title}</span>
        <span className="text-muted-foreground"> · {s.state}{s.doing ? ` · ${s.doing}` : ""}</span>
      </Row>)}
      {now.errands.map((e) => <Row key={e.id} label={t("town.errandFor", { defaultValue: "Errand · {{who}}", who: e.resident })}>
        {e.task} <span className="text-muted-foreground">· {e.status}</span>
      </Row>)}
    </Section>
    {finished.length > 0 && <Section title={t("town.justFinished", { defaultValue: "Just finished" })}>
      {finished.map((a) => <ActivityRow key={a.key} entry={a} />)}
    </Section>}
  </>;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="settings-list-row flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2.5 text-[13px] animate-in fade-in-0 duration-300 motion-reduce:animate-none">
    <span className="w-28 shrink-0 text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
    <span className="min-w-0 flex-1">{children}</span>
  </div>;
}

function ActivityRow({ entry }: { entry: TownActivity }) {
  const { t } = useTranslation();
  const Icon = entry.status === "running" ? Loader2 : entry.status === "waiting" ? Clock : entry.status === "done" ? CheckCircle2 : AlertCircle;
  const when = entry.active ? t("town.forTime", { defaultValue: "for {{time}}", time: ago(entry.started) })
    : t("town.timeAgo", { defaultValue: "{{time}} ago", time: ago(entry.finished || entry.started) });
  return <div data-status={entry.status} className="settings-list-row flex items-start gap-2 py-2.5 text-[13px] animate-in fade-in-0 duration-300 motion-reduce:animate-none">
    <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", entry.status === "running" && "animate-spin text-foreground",
      entry.status === "done" && "text-emerald-500", entry.status === "failed" && "text-destructive", entry.status === "waiting" && "text-muted-foreground")} aria-label={entry.status} />
    <span className="min-w-0 flex-1">
      <span className="font-medium">{entry.label}</span>
      {entry.detail && <span className={cn(entry.status === "failed" ? "text-destructive" : "text-muted-foreground")}> · {entry.detail}</span>}
    </span>
    <span className="shrink-0 text-xs text-muted-foreground">{when}</span>
  </div>;
}

function Logs({ onError }: { onError: (message: string) => void }) {
  const { t } = useTranslation();
  const { getToken } = useClient();
  const [service, setService] = useState("gateway");
  const [level, setLevel] = useState("INFO");
  const [logs, setLogs] = useState<TownLogs | null>(null);
  const box = useRef<HTMLPreElement>(null);
  const load = useCallback(async () => {
    try { setLogs(await fetchTownLogs(getToken(), service, level)); } catch (reason) { onError(reason instanceof Error ? reason.message : String(reason)); }
  }, [getToken, level, onError, service]);
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void load(); }, LOGS_MS);
    return () => window.clearInterval(timer);
  }, [load]);
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [logs]);
  const labels: Record<string, string> = {
    gateway: t("town.logGateway", { defaultValue: "Gateway" }), queue: t("town.logQueue", { defaultValue: "Model queue" }),
    upkeep: t("town.logUpkeep", { defaultValue: "Upkeep" }),
  };
  return <Section title={t("town.logs", { defaultValue: "Logs" })}>
    <div className="settings-list-row flex flex-wrap items-center gap-3 py-3">
      <SegmentedControl<string> value={service} onChange={setService} ariaLabel={t("town.logService", { defaultValue: "Which service" })}
        options={(logs?.services ?? ["gateway", "queue", "upkeep"]).map((s) => ({ value: s, label: labels[s] ?? s }))} />
      <label className="flex items-center gap-2 text-[13px]">
        {t("town.logLevel", { defaultValue: "Show" })}
        <select className="rounded border bg-background px-1 py-0.5 text-[13px]" value={level} onChange={(event) => setLevel(event.target.value)}>
          <option value="DEBUG">{t("town.logEverything", { defaultValue: "everything" })}</option>
          <option value="INFO">{t("town.logInfo", { defaultValue: "info and up" })}</option>
          <option value="WARNING">{t("town.logWarnings", { defaultValue: "warnings and errors" })}</option>
          <option value="ERROR">{t("town.logErrors", { defaultValue: "errors only" })}</option>
        </select>
      </label>
    </div>
    <div className="settings-list-row py-3">
      {logs && logs.entries.length === 0
        ? <p className="text-[13px] text-muted-foreground">{t("town.logEmpty", { defaultValue: "Nothing logged yet. The service writes its log once it's been restarted on this version." })}</p>
        : <pre ref={box} aria-label={t("town.logEntries", { defaultValue: "Log entries" })}
          className="max-h-[28rem] overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/60 p-3 font-mono text-[11.5px] leading-5">
          {(logs?.entries ?? []).map((e, i) => <span key={i} className={cn("block", e.level === "WARNING" && "text-amber-700 dark:text-amber-300",
            (e.level === "ERROR" || e.level === "CRITICAL") && "text-destructive", e.level === "DEBUG" && "text-muted-foreground")}>{e.text}</span>)}
        </pre>}
    </div>
  </Section>;
}
