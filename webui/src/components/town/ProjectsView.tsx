import { useCallback, useEffect, useState } from "react";
import { Loader2, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { TownIntro, TownSection } from "@/components/town/TownLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ToggleButton } from "@/components/ui/toggle-button";
import { useClient } from "@/providers/ClientProvider";
import { changeProjectBoard, fetchTownProjects, type TownProject, type TownProjects, type TownTicket } from "@/lib/api";
import { cn } from "@/lib/utils";

const COLUMN_TONE: Record<string, string> = {
  open: "border-t-sky-400/70", doing: "border-t-amber-400/80", blocked: "border-t-destructive/70", done: "border-t-emerald-500/70",
};
const SELECT = "rounded border bg-background px-1 py-0.5 text-[13px]";

/** The projects board: the same as `babo projects` (and what residents see with `project_board`). */
export function ProjectsView({ residents, onError }: { residents: string[]; onError: (message: string) => void }) {
  const { t } = useTranslation();
  const { client, getToken } = useClient();
  const [board, setBoard] = useState<TownProjects | null>(null);
  const [open, setOpen] = useState<string>("");
  const [adding, setAdding] = useState(false);
  const [said, setSaid] = useState("");
  const load = useCallback(async () => {
    try { setBoard(await fetchTownProjects(getToken())); } catch (reason) { onError(reason instanceof Error ? reason.message : String(reason)); }
  }, [getToken, onError]);
  useEffect(() => { void load(); }, [load]);
  const change = useCallback(async (what: Record<string, string | boolean>) => {
    try {
      const result = await changeProjectBoard(client, what);
      setBoard(result.projects);
      setSaid(result.message);
      return true;
    } catch (reason) { onError(reason instanceof Error ? reason.message : String(reason)); return false; }
  }, [client, onError]);

  if (!board) return <p className="settings-list-inset text-[13px] text-muted-foreground"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />{t("town.loading", { defaultValue: "Loading the town…" })}</p>;
  const project = board.projects.find((p) => p.slug === open) ?? null;
  return <>
    <TownIntro>
      {t("town.projectsIntro", { defaultValue: "The town's projects and their tickets. Residents start projects, claim tickets and keep them up to date with project_board; in the terminal: babo projects." })}
    </TownIntro>
    {said && <p role="status" className="settings-list-inset text-[13px] text-emerald-700 animate-in fade-in-0 dark:text-emerald-300">{said}</p>}
    <TownSection title={t("town.projects", { defaultValue: "Projects" })}
      description={t("town.projectsPick", { defaultValue: "Pick one to see its tickets." })}>
        {board.projects.length === 0 && <p className="settings-list-row py-3 text-[13px] text-muted-foreground">{t("town.noProjects", { defaultValue: "No projects yet." })}</p>}
        {board.projects.map((p) => <button key={p.slug} type="button" aria-pressed={p.slug === open} onClick={() => setOpen(p.slug === open ? "" : p.slug)}
          className={cn("settings-list-row flex w-full flex-wrap items-baseline gap-x-3 gap-y-1 py-2.5 text-left text-[13px] transition-colors hover:bg-muted/40",
            p.slug === open && "bg-muted/50")}>
          <span className="font-medium">{p.title}</span>
          <span className="text-muted-foreground">{p.status} · {t("town.projectLead", { defaultValue: "lead {{who}}", who: p.lead })}</span>
          {p.help_wanted && <span className="rounded-full bg-sky-500/15 px-2 text-xs text-sky-800 dark:text-sky-200">{t("town.helpWanted", { defaultValue: "help wanted" })}</span>}
          <span className="ml-auto text-xs text-muted-foreground">
            {t("town.projectCounts", { defaultValue: "{{open}} open · {{doing}} doing · {{blocked}} blocked · {{done}} done", ...p.counts })}
          </span>
        </button>)}
        <div className="settings-list-row py-2.5">
          {adding
            ? <NewProject residents={residents} onCancel={() => setAdding(false)} onSubmit={async (what) => {
              if (await change(what)) { setAdding(false); setOpen(String(what.title).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40)); }
            }} />
            : <Button type="button" variant="outline" size="sm" onClick={() => setAdding(true)}><Plus className="mr-1 h-4 w-4" />{t("town.newProject", { defaultValue: "New project" })}</Button>}
        </div>
    </TownSection>
    {project && <ProjectBoard key={project.slug} project={project} statuses={board.statuses} projectStatuses={board.project_statuses}
      residents={residents} change={change} />}
  </>;
}

function NewProject({ residents, onSubmit, onCancel }: {
  residents: string[]; onSubmit: (what: Record<string, string | boolean>) => Promise<void>; onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [lead, setLead] = useState("");
  const [wanted, setWanted] = useState(false);
  const [busy, setBusy] = useState(false);
  return <form className="flex flex-col gap-2" aria-label={t("town.newProject", { defaultValue: "New project" })} onSubmit={(event) => {
    event.preventDefault();
    setBusy(true);
    void onSubmit({ action: "new_project", title, description, help_wanted: wanted, ...(lead ? { lead } : {}) }).finally(() => setBusy(false));
  }}>
    <Input aria-label={t("town.projectTitle", { defaultValue: "Title" })} placeholder={t("town.projectTitle", { defaultValue: "Title" })}
      value={title} maxLength={120} onChange={(event) => setTitle(event.target.value)} />
    <textarea aria-label={t("town.projectAbout", { defaultValue: "What it is, and what done looks like" })} className="min-h-16 rounded-md border bg-background px-2 py-1 text-[13px]"
      placeholder={t("town.projectAbout", { defaultValue: "What it is, and what done looks like" })} value={description} onChange={(event) => setDescription(event.target.value)} />
    <div className="flex flex-wrap items-center gap-3 text-[13px]">
      <label className="flex items-center gap-2">{t("town.projectLeadLabel", { defaultValue: "Lead" })}
        <select className={SELECT} value={lead} onChange={(event) => setLead(event.target.value)}>
          <option value="">{t("town.you", { defaultValue: "you" })}</option>
          {residents.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </label>
      <span className="flex items-center gap-2"><ToggleButton checked={wanted} onChange={setWanted} label={t("town.askForHelp", { defaultValue: "Help wanted" })} />
        {t("town.askForHelp", { defaultValue: "Help wanted" })}</span>
      <span className="ml-auto flex gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>{t("common.cancel", { defaultValue: "Cancel" })}</Button>
        <Button type="submit" size="sm" disabled={busy || !title.trim()}>{t("town.startProject", { defaultValue: "Start it" })}</Button>
      </span>
    </div>
  </form>;
}

type Change = (what: Record<string, string | boolean>) => Promise<boolean>;

function ProjectBoard({ project, statuses, projectStatuses, residents, change }: {
  project: TownProject; statuses: string[]; projectStatuses: string[]; residents: string[]; change: Change;
}) {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  return <TownSection title={project.title} description={project.description || undefined}
    badges={<span className="text-xs font-normal text-muted-foreground">{t("town.projectLead", { defaultValue: "lead {{who}}", who: project.lead })}</span>}
    actions={<>
      <label className="flex items-center gap-2">{t("town.projectStatus", { defaultValue: "Status" })}
        <select className={SELECT} value={project.status} onChange={(event) => void change({ action: "update_project", project: project.slug, status: event.target.value })}>
          {projectStatuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      <span className="flex items-center gap-2 text-[13px]"><ToggleButton checked={project.help_wanted} label={t("town.askForHelp", { defaultValue: "Help wanted" })}
        onChange={(help) => void change({ action: "update_project", project: project.slug, help_wanted: help })} />
        {t("town.askForHelp", { defaultValue: "Help wanted" })}</span>
    </>}>
    <form className="settings-list-row flex gap-2 py-3" onSubmit={(event) => {
      event.preventDefault();
      void change({ action: "new_ticket", project: project.slug, title }).then((ok) => { if (ok) setTitle(""); });
    }}>
      <Input aria-label={t("town.newTicket", { defaultValue: "A new ticket" })} placeholder={t("town.newTicket", { defaultValue: "A new ticket" })}
        value={title} maxLength={120} onChange={(event) => setTitle(event.target.value)} />
      <Button type="submit" size="sm" disabled={!title.trim()}><Plus className="mr-1 h-4 w-4" />{t("town.addTicket", { defaultValue: "Add" })}</Button>
    </form>
    <div className="grid gap-3 p-3 sm:grid-cols-2 xl:grid-cols-4">
      {statuses.map((status) => {
        const tickets = project.tickets.filter((x) => x.status === status);
        return <section key={status} aria-label={status} className={cn("rounded-lg border border-t-4 bg-muted/20 p-2", COLUMN_TONE[status])}>
          <h3 className="mb-2 flex items-baseline justify-between px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {status}<span className="font-normal">{tickets.length}</span>
          </h3>
          <div className="flex flex-col gap-2">
            {tickets.length === 0 && <p className="px-1 text-xs text-muted-foreground">{t("town.noTickets", { defaultValue: "Nothing here." })}</p>}
            {tickets.map((ticket) => <TicketCard key={ticket.ref} ticket={ticket} statuses={statuses} residents={residents} change={change} />)}
          </div>
        </section>;
      })}
    </div>
  </TownSection>;
}

function TicketCard({ ticket, statuses, residents, change }: { ticket: TownTicket; statuses: string[]; residents: string[]; change: Change }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [note, setNote] = useState("");
  const [status, setStatus] = useState(ticket.status);
  const needsWhy = status === "blocked" && ticket.status !== "blocked" && !note.trim();
  return <article aria-label={ticket.ref} className="rounded-md border bg-background p-2 text-[13px] shadow-sm animate-in fade-in-0 duration-300 motion-reduce:animate-none">
    <button type="button" className="w-full text-left" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
      <span className="text-xs text-muted-foreground">{ticket.ref}</span>
      <span className="block font-medium">{ticket.title}</span>
      <span className="text-xs text-muted-foreground">{ticket.assignee || t("town.nobodyHasIt", { defaultValue: "nobody has it" })}</span>
    </button>
    {expanded && <div className="mt-2 flex flex-col gap-2 border-t pt-2">
      {ticket.description && <p className="whitespace-pre-wrap">{ticket.description}</p>}
      {ticket.notes.length > 0 && <ul className="flex flex-col gap-0.5 text-xs text-muted-foreground">
        {ticket.notes.map((n, i) => <li key={i}>{n.replace(/^- /, "")}</li>)}
      </ul>}
      <div className="flex flex-wrap gap-2">
        <select aria-label={t("town.ticketStatus", { defaultValue: "Status" })} className={SELECT} value={status} onChange={(event) => setStatus(event.target.value)}>
          {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select aria-label={t("town.whoHasIt", { defaultValue: "Who has it" })} className={SELECT} value={ticket.assignee}
          onChange={(event) => void change({ action: "update_ticket", ticket: ticket.ref, assignee: event.target.value })}>
          <option value="">{t("town.nobody", { defaultValue: "nobody" })}</option>
          {residents.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>
      <textarea aria-label={t("town.ticketNote", { defaultValue: "A note" })} className="min-h-12 rounded-md border bg-background px-2 py-1 text-[13px]"
        placeholder={status === "blocked" ? t("town.blockedOn", { defaultValue: "What it's blocked on" }) : t("town.ticketNote", { defaultValue: "A note" })}
        value={note} onChange={(event) => setNote(event.target.value)} />
      <Button type="button" size="sm" disabled={needsWhy || (status === ticket.status && !note.trim())}
        onClick={() => void change({ action: "update_ticket", ticket: ticket.ref, note, ...(status !== ticket.status ? { status } : {}) })
          .then((ok) => { if (ok) setNote(""); })}>
        {t("town.saveTicket", { defaultValue: "Save" })}
      </Button>
    </div>}
  </article>;
}
