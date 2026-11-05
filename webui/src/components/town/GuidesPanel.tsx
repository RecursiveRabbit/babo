import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { TownSection } from "@/components/town/TownLayout";
import { useClient } from "@/providers/ClientProvider";
import { fetchTownGuides, type TownGuide } from "@/lib/api";

/** The guides Babo brings in at the right moment: what brings each in, and how often. The same as `babo guides`. */
export function GuidesPanel() {
  const { t } = useTranslation();
  const { getToken } = useClient();
  const [guides, setGuides] = useState<TownGuide[] | null>(null);
  useEffect(() => { fetchTownGuides(getToken()).then((r) => setGuides(r.guides ?? [])).catch(() => setGuides(null)); }, [getToken]);
  if (!guides || guides.length === 0) return null;
  return <TownSection title={t("town.guidesTitle", { defaultValue: "Guides and skills" })} description={t("town.guidesIntro", { defaultValue: "Short notes Babo brings in when they're needed: with the first use of a tool in a session, or after a refusal. Every agent sees their names; any can open one by hand. They're notes in commons/guides: change them or add your own. Skills (commons/skills, written by the Archivist) come the same way, and also when a message has one of their keywords." })}>
      {guides.map((g) => <div key={g.name} className="settings-list-row py-3 text-[13px]">
        <span className="block font-medium">{g.title} <span className="font-normal text-muted-foreground">· {g.kind === "skill" ? t("town.skill", { defaultValue: "skill" }) : g.name}</span></span>
        <span className="mt-0.5 block text-xs text-muted-foreground">
          {g.when}
          {" · "}{[...g.tools.map((tool) => t("town.guideTool", { defaultValue: "first {{tool}}", tool })), ...(g.errors.length ? [t("town.guideError", { defaultValue: "an error" })] : []),
            ...(g.keywords ?? []).map((word) => t("town.guideKeyword", { defaultValue: "“{{word}}” in a message", word }))].join(", ")}
          {g.offices.length ? ` · ${g.offices.join(", ")}` : ""}
          {" · "}{t("town.guideCounts", { defaultValue: "brought in {{brought}}×, opened by hand {{opened}}×", brought: g.brought, opened: g.opened })}
        </span>
        {g.hint && <span className="mt-0.5 block text-xs text-amber-600 dark:text-amber-400">{g.hint}</span>}
      </div>)}
  </TownSection>;
}
