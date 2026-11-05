import { useCallback, useEffect, useState } from "react";
import { Loader2, MessageSquarePlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { TownIntro, TownSection } from "@/components/town/TownLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useClient } from "@/providers/ClientProvider";
import { changeSquare, fetchTownSquare, type TownSquare, type TownThread } from "@/lib/api";
import { cn } from "@/lib/utils";

const KIND_TONE: Record<string, string> = {
  question: "bg-sky-500/15 text-sky-800 dark:text-sky-200", observation: "bg-muted text-foreground",
  flag: "bg-amber-500/20 text-amber-900 dark:text-amber-200", announcement: "bg-emerald-500/15 text-emerald-800 dark:text-emerald-200",
};
const when = (iso: string) => iso.slice(0, 16).replace("T", " ");

/** The town square: the same as `babo square` (and `town_square` for residents). */
export function SquareView({ onError }: { onError: (message: string) => void }) {
  const { t } = useTranslation();
  const { client, getToken } = useClient();
  const [square, setSquare] = useState<TownSquare | null>(null);
  const [said, setSaid] = useState("");
  const [writing, setWriting] = useState(false);
  const [showClosed, setShowClosed] = useState(false);
  const load = useCallback(async () => {
    try { setSquare(await fetchTownSquare(getToken())); } catch (reason) { onError(reason instanceof Error ? reason.message : String(reason)); }
  }, [getToken, onError]);
  useEffect(() => { void load(); }, [load]);
  const change = useCallback(async (what: Record<string, string>) => {
    try {
      const result = await changeSquare(client, what);
      setSquare(result.square);
      setSaid(result.message);
      return true;
    } catch (reason) { onError(reason instanceof Error ? reason.message : String(reason)); return false; }
  }, [client, onError]);
  if (!square) return <p className="settings-list-inset text-[13px] text-muted-foreground"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />{t("town.loading", { defaultValue: "Loading the town…" })}</p>;
  const open = square.threads.filter((x) => x.status === "open");
  const closed = square.threads.filter((x) => x.status !== "open");
  return <>
    <TownIntro>
      {t("town.squareIntro", { defaultValue: "Threads anyone in the town starts and replies to: questions, observations, flags and announcements. Residents see what's new at the start of their next session. In the terminal: babo square." })}
    </TownIntro>
    {said && <p role="status" className="settings-list-inset text-[13px] text-emerald-700 animate-in fade-in-0 dark:text-emerald-300">{said}</p>}
    <TownSection title={t("town.squareOpen", { defaultValue: "Open threads" })}
      description={t("town.squareOpenHelp", { defaultValue: "Newest activity first. Open one to read it and reply." })}>
        <div className="settings-list-row py-2.5">
          {writing
            ? <NewThread kinds={square.kinds} onCancel={() => setWriting(false)} onSubmit={async (what) => { if (await change(what)) setWriting(false); }} />
            : <Button type="button" variant="outline" size="sm" onClick={() => setWriting(true)}>
              <MessageSquarePlus className="mr-1 h-4 w-4" />{t("town.newThread", { defaultValue: "Start a thread" })}
            </Button>}
        </div>
        {open.length === 0 && <p className="settings-list-row py-3 text-[13px] text-muted-foreground">{t("town.squareQuiet", { defaultValue: "The square is quiet: no open threads." })}</p>}
        {open.map((thread) => <Thread key={thread.id} thread={thread} change={change} />)}
    </TownSection>
    {closed.length > 0 && <section aria-label={t("town.squareClosed", { defaultValue: "Closed threads" })}>
      <Button type="button" variant="outline" size="sm" className="settings-list-inset" aria-expanded={showClosed} onClick={() => setShowClosed(!showClosed)}>
        {t("town.closedThreads", { defaultValue: "Closed threads ({{count}})", count: closed.length })}
      </Button>
      {showClosed && <div className="mt-2 overflow-hidden rounded-panel border border-border/70 bg-settings-surface">{closed.map((thread) => <Thread key={thread.id} thread={thread} change={change} />)}</div>}
    </section>}
  </>;
}

function NewThread({ kinds, onSubmit, onCancel }: { kinds: string[]; onSubmit: (what: Record<string, string>) => Promise<void>; onCancel: () => void }) {
  const { t } = useTranslation();
  const [kind, setKind] = useState(kinds.includes("announcement") ? "announcement" : kinds[0] ?? "");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  return <form className="flex flex-col gap-2" aria-label={t("town.newThread", { defaultValue: "Start a thread" })} onSubmit={(event) => {
    event.preventDefault();
    setBusy(true);
    void onSubmit({ action: "post", kind, title, text }).finally(() => setBusy(false));
  }}>
    <div className="flex flex-wrap gap-2">
      <select aria-label={t("town.threadKind", { defaultValue: "Kind" })} className="rounded border bg-background px-1 py-1 text-[13px]" value={kind}
        onChange={(event) => setKind(event.target.value)}>
        {kinds.map((k) => <option key={k} value={k}>{k}</option>)}
      </select>
      <Input className="min-w-48 flex-1" aria-label={t("town.threadTitle", { defaultValue: "Title" })} placeholder={t("town.threadTitle", { defaultValue: "Title" })}
        value={title} maxLength={120} onChange={(event) => setTitle(event.target.value)} />
    </div>
    <textarea aria-label={t("town.threadText", { defaultValue: "What it's about" })} className="min-h-20 rounded-md border bg-background px-2 py-1 text-[13px]"
      placeholder={t("town.threadText", { defaultValue: "What it's about" })} value={text} onChange={(event) => setText(event.target.value)} />
    <span className="flex justify-end gap-2">
      <Button type="button" variant="ghost" size="sm" onClick={onCancel}>{t("common.cancel", { defaultValue: "Cancel" })}</Button>
      <Button type="submit" size="sm" disabled={busy || !text.trim()}>{t("town.postThread", { defaultValue: "Post" })}</Button>
    </span>
  </form>;
}

function Thread({ thread, change }: { thread: TownThread; change: (what: Record<string, string>) => Promise<boolean> }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [reply, setReply] = useState("");
  const isOpen = thread.status === "open";
  return <article aria-label={thread.title} className="settings-list-row py-2.5 text-[13px] animate-in fade-in-0 duration-300 motion-reduce:animate-none">
    <button type="button" className="flex w-full flex-wrap items-baseline gap-x-2 gap-y-1 text-left" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
      <span className={cn("rounded-full px-2 text-xs", KIND_TONE[thread.kind] ?? "bg-muted")}>{thread.kind}</span>
      <span className="font-medium">{thread.title}</span>
      <span className="text-muted-foreground">{thread.author}</span>
      <span className="ml-auto text-xs text-muted-foreground">
        {thread.replies.length ? (thread.replies.length === 1 ? t("town.oneReply", { defaultValue: "1 reply" })
          : t("town.replyCount", { defaultValue: "{{count}} replies", count: thread.replies.length })) + " · " : ""}{when(thread.updated || thread.created)}
      </span>
    </button>
    {expanded && <div className="mt-2 flex flex-col gap-2 border-l-2 pl-3">
      <p className="whitespace-pre-wrap">{thread.text}</p>
      {thread.replies.map((r, i) => <p key={i}><span className="font-medium">{r.by}</span> <span className="text-xs text-muted-foreground">{when(r.at)}</span><br />{r.text}</p>)}
      {!isOpen && <p className="text-xs text-muted-foreground">{t("town.closedBy", { defaultValue: "Closed by {{who}}.", who: thread.closed_by })}</p>}
      {isOpen && <form className="flex flex-col gap-2" onSubmit={(event) => {
        event.preventDefault();
        void change({ action: "reply", thread: thread.id, text: reply }).then((ok) => { if (ok) setReply(""); });
      }}>
        <textarea aria-label={t("town.yourReply", { defaultValue: "Your reply" })} className="min-h-12 rounded-md border bg-background px-2 py-1 text-[13px]"
          value={reply} onChange={(event) => setReply(event.target.value)} />
        <span className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => void change({ action: "close", thread: thread.id, text: reply })}>
            {t("town.closeThread", { defaultValue: "Close it" })}
          </Button>
          <Button type="submit" size="sm" disabled={!reply.trim()}>{t("town.reply", { defaultValue: "Reply" })}</Button>
        </span>
      </form>}
    </div>}
  </article>;
}
