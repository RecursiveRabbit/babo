import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, PauseCircle, PlayCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useClient } from "@/providers/ClientProvider";
import { officeAgentAction, fetchOffice, fetchOfficeOp, type OfficeAgent, type OfficeOp, type OfficeView } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATE_TONE: Record<string, string> = {
  running: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/40",
  frozen: "bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/40",
  starting: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/40",
  dead: "bg-destructive/15 text-destructive border-destructive/40",
  missing: "bg-destructive/10 text-destructive border-destructive/30",
  drifted: "bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30",
  unmanaged: "bg-muted text-muted-foreground border-border",
  unknown: "bg-muted text-muted-foreground border-border",
};

/** The office: projects with one lead and a crew, and the agents they run as.
 *  Live state is the Manager's answer; a lifecycle verb shows pending until the
 *  Manager settles it, and its refusal or failure in the Manager's own words. */
export function OfficePage({ onBackToChat }: { onBackToChat: () => void }) {
  const { t } = useTranslation();
  const { client, getToken } = useClient();
  const [view, setView] = useState<OfficeView | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string>("");
  const [result, setResult] = useState<{ handle: string; text: string; state: string } | null>(null);
  const alive = useRef(true);

  const load = useCallback(async () => {
    try {
      setView(await fetchOffice(getToken()));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [getToken]);

  useEffect(() => {
    alive.current = true;
    void load();
    const timer = window.setInterval(() => { void load(); }, 5000);
    return () => { alive.current = false; window.clearInterval(timer); };
  }, [load]);

  const act = useCallback(async (handle: string, verb: "wake" | "freeze") => {
    setBusy(handle);
    setResult({ handle, text: t("office.pending", { defaultValue: "Asking the Manager…" }), state: "pending" });
    try {
      const started = await officeAgentAction(client, handle, verb, verb === "wake" ? "owner: wake from the office" : "owner: freeze from the office");
      let op: OfficeOp = started.op;
      while (alive.current && (op.state === "pending" || op.state === "running")) {
        await new Promise((resolve) => window.setTimeout(resolve, 700));
        op = await fetchOfficeOp(getToken(), op.id);
        setResult({ handle, text: op.said || t("office.running", { defaultValue: "The Manager is working on it…" }), state: op.state });
      }
      setResult({ handle, text: op.said || op.state, state: op.state });
    } catch (reason) {
      setResult({ handle, text: reason instanceof Error ? reason.message : String(reason), state: "failed" });
    } finally {
      if (alive.current) { setBusy(""); void load(); }
    }
  }, [client, getToken, load, t]);

  if (!view) {
    return <div className="p-6 text-[13px] text-muted-foreground">
      <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
      {error || t("office.loading", { defaultValue: "Reading the office…" })}
    </div>;
  }

  const agentOf = (handle: string): OfficeAgent | undefined => view.agents.find((a) => a.handle === handle);

  return <div className="flex h-full flex-col overflow-y-auto">
    <header className="flex items-center justify-between border-b px-6 py-4">
      <div>
        <h1 className="text-lg font-semibold">{t("office.title", { defaultValue: "Office" })}</h1>
        <p className="text-[13px] text-muted-foreground">
          {t("office.intro", { defaultValue: "Each project has one lead and a crew. Desired state is yours; what is running is the Manager's answer." })}
        </p>
      </div>
      <Button variant="ghost" size="sm" onClick={onBackToChat}>{t("office.back", { defaultValue: "Back to chat" })}</Button>
    </header>

    {!view.manager.available && <p role="status" className="mx-6 mt-4 rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[13px]">
      {t("office.managerDown", { defaultValue: "The Manager can't be read: {{said}}. Nothing below is shown as running until it answers.", said: view.manager.said })}
    </p>}
    {error && <p role="alert" className="mx-6 mt-4 rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-[13px]">{error}</p>}

    <div className="grid gap-4 p-6">
      {view.projects.length === 0 && <p className="text-[13px] text-muted-foreground">{t("office.noProjects", { defaultValue: "No projects yet. Start one in the Town page's Projects board, or from the terminal." })}</p>}
      {view.projects.map((project) => <section key={project.slug} className="rounded-lg border bg-card p-4">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <div>
            <h2 className="text-[15px] font-medium">{project.title}</h2>
            <p className="text-[12px] text-muted-foreground">
              {project.slug} · {project.open_tickets} open {t("office.tickets", { defaultValue: "tickets" })}
            </p>
          </div>
          <span className="text-[12px] text-muted-foreground">
            {t("office.lead", { defaultValue: "Lead" })}: {project.lead || t("office.none", { defaultValue: "unset" })}
            {" · "}
            {t("office.crew", { defaultValue: "Crew" })}: {project.crew.length}
          </span>
        </div>
        {project.agents.length === 0 && <p className="text-[13px] text-muted-foreground">{t("office.noAgents", { defaultValue: "No agents recorded for this project yet." })}</p>}
        <ul className="grid gap-2">
          {project.agents.map((handle) => {
            const agent = agentOf(handle);
            const status = agent?.status ?? "unknown";
            const tone = STATE_TONE[status] ?? STATE_TONE.unknown;
            const canWake = status === "frozen" || status === "dead" || status === "drifted" || status === "unknown";
            return <li key={handle} className="flex flex-wrap items-center gap-3 rounded border px-3 py-2">
              <span className="min-w-40 font-mono text-[13px]">{handle}</span>
              <span className={cn("rounded border px-2 py-0.5 text-[12px]", tone)}>{status}</span>
              {agent?.role && <span className="text-[12px] text-muted-foreground">{agent.role === "lead" ? t("office.lead", { defaultValue: "Lead" }) : t("office.crewMember", { defaultValue: "Crew" })}</span>}
              {agent?.wg_address && <span className="font-mono text-[11px] text-muted-foreground">{agent.wg_address}</span>}
              {agent?.checkouts.length ? <span className="text-[11px] text-muted-foreground">{t("office.checkouts", { defaultValue: "{{n}} live checkout(s)", n: agent.checkouts.length })}</span> : null}
              <span className="ml-auto flex gap-2">
                <Button size="sm" variant="outline" disabled={busy === handle || !canWake}
                  onClick={() => void act(handle, "wake")}>
                  <PlayCircle className="mr-1 h-4 w-4" />{t("office.wake", { defaultValue: "Wake" })}
                </Button>
                <Button size="sm" variant="outline" disabled={busy === handle || status !== "running"}
                  onClick={() => void act(handle, "freeze")}>
                  <PauseCircle className="mr-1 h-4 w-4" />{t("office.freeze", { defaultValue: "Freeze" })}
                </Button>
              </span>
              {agent?.said && <p className="w-full text-[12px] text-muted-foreground">{agent.said}</p>}
            </li>;
          })}
        </ul>
      </section>)}
      {result && <p role="status" className={cn("rounded border px-3 py-2 text-[13px]",
        result.state === "succeeded" ? "border-emerald-500/40 bg-emerald-500/10" :
        result.state === "failed" || result.state === "refused" || result.state === "timeout" ? "border-destructive/40 bg-destructive/10" : "border-border bg-muted/40")}>
        <span className="font-mono">{result.handle}</span>: {result.text}
      </p>}
      <p className="text-[12px] text-muted-foreground">
        {t("office.freezeNote", { defaultValue: "A freeze is a pause: the work is kept, the peer is removed, and the Manager's ledger says so. It is not a stop-and-save." })}
      </p>
    </div>
  </div>;
}
