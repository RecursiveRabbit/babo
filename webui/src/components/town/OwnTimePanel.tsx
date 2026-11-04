import { useCallback, useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { SettingsGroup } from "@/components/settings/shared/SettingsControls";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { ActivityLine, refreshActivity } from "@/components/town/ActivityLine";
import { useClient } from "@/providers/ClientProvider";
import { fetchTownOwnTime, giveOwnTimeNow, setTownOwnTime, type TownOwnTime } from "@/lib/api";

const when = (iso: string) => iso.slice(0, 16).replace("T", " ");

/** Own time, beside the rounds: how often each resident has a slot that is its own, and what it did with the last one.
 *  The same as `babo own-time`. */
export function OwnTimePanel({ onNotice, onError }: { onNotice: (message: string) => void; onError: (message: string) => void }) {
  const { t } = useTranslation();
  const { client, getToken } = useClient();
  const [data, setData] = useState<TownOwnTime | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setData(await fetchTownOwnTime(getToken())); } catch { setData(null); }  // (an older Babo: no own time)
  }, [getToken]);
  useEffect(() => { void load(); }, [load]);
  const act = async (run: () => Promise<{ message: string; own_time: TownOwnTime }>) => {
    setBusy(true);
    try {
      const result = await run();
      setData(result.own_time);
      onNotice(result.message);
      refreshActivity();
    } catch (reason) { onError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };
  if (!data || !Array.isArray(data.residents) || !Array.isArray(data.choices)) return null;
  const label = (every: string) => ({
    daily: t("town.ownTimeDaily", { defaultValue: "Daily" }), weekly: t("town.ownTimeWeekly", { defaultValue: "Weekly" }),
    off: t("town.ownTimeOff", { defaultValue: "Off" }), town: t("town.ownTimeTown", { defaultValue: "As the town" }),
  })[every] ?? every;
  return <section aria-label={t("town.ownTime", { defaultValue: "Own time" })} className="mt-4">
    <h2 className="settings-list-inset text-[13px] font-medium text-foreground">{t("town.ownTime", { defaultValue: "Own time" })}</h2>
    <p className="settings-list-inset text-xs text-muted-foreground">
      {t("town.ownTimeIntro", { defaultValue: "A slot for each resident that is its own: nothing is asked of it. It might look back on its work, revise itself, write a lesson or a letter, move a project of its own on, or rest. It runs when the model is free; Babo keeps only the few lines it says about it." })}
    </p>
    <SettingsGroup>
      <div className="settings-list-row flex flex-wrap items-center gap-3 py-3 text-[13px]">
        <span className="font-medium">{t("town.ownTimeForTown", { defaultValue: "For the town" })}</span>
        <SegmentedControl<string> value={data.every} ariaLabel={t("town.ownTimeForTown", { defaultValue: "For the town" })}
          onChange={(every) => void act(() => setTownOwnTime(client, every))}
          options={data.choices.map((c) => ({ value: c, label: label(c) }))} />
      </div>
      {data.residents.map((row) => {
        const last = row.recent[0];
        return <div key={row.resident} className="settings-list-row py-3 text-[13px]">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span className="font-medium">{row.name || row.resident}</span>
            <span className="text-xs text-muted-foreground">{row.office}</span>
            <select aria-label={t("town.ownTimeFor", { defaultValue: "Own time for {{who}}", who: row.resident })} disabled={busy}
              className="rounded border bg-background px-1 py-0.5 text-[13px]" value={row.own_setting ? row.every : "town"}
              onChange={(event) => void act(() => setTownOwnTime(client, event.target.value, row.resident))}>
              {["town", ...data.choices].map((c) => <option key={c} value={c}>{label(c)}</option>)}
            </select>
            <span className="text-xs text-muted-foreground">
              {row.next ? t("town.ownTimeNext", { defaultValue: "next: {{when}}", when: row.next.includes("T") ? when(row.next) : row.next })
                : t("town.ownTimeIsOff", { defaultValue: "off" })}
            </span>
            <Button type="button" variant="outline" size="sm" className="ml-auto gap-1" disabled={busy}
              onClick={() => void act(() => giveOwnTimeNow(client, row.resident))}>
              <Sparkles className="h-4 w-4" />{t("town.ownTimeNow", { defaultValue: "Give it its time now" })}
            </Button>
          </div>
          <ActivityLine activityKey={`own_time:${row.resident}`} />
          {last && <p className="mt-1 text-xs text-muted-foreground">
            {t("town.ownTimeLast", { defaultValue: "Last ({{when}}):", when: when(last.started) })}{" "}
            <span className={last.status === "failed" ? "text-destructive" : "text-foreground"}>{last.said}</span>
          </p>}
        </div>;
      })}
    </SettingsGroup>
  </section>;
}
