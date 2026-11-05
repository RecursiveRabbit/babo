import { useId, type Dispatch, type SetStateAction } from "react";
import { Check, Monitor, Moon, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";

import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { SettingsGroup, SettingsRow, SettingsSectionTitle } from "@/components/settings/shared/SettingsControls";
import { SettingsHint } from "@/components/settings/shared/SettingsHint";
import { ToggleButton } from "@/components/ui/toggle-button";
import { SegmentedControl } from "@/components/ui/segmented-control";
import type { ThemePreference } from "@/hooks/useTheme";
import { ACCENTS, useAccent, type Accent } from "@/lib/accent";
import { cn } from "@/lib/utils";
import type { FileEditDisplayMode, LocalActivityMode, LocalPreferences } from "@/lib/local-preferences";
import { ReadingSettings } from "./ReadingSettings";
import "./appearance-settings.css";

export function AppearanceSettingsView({ themePreference, onChangeTheme, localPrefs, onChangeLocalPrefs }: {
  themePreference: ThemePreference;
  onChangeTheme: (preference: ThemePreference) => void;
  localPrefs: LocalPreferences;
  onChangeLocalPrefs: Dispatch<SetStateAction<LocalPreferences>>;
}) {
  const { t } = useTranslation();
  const themeId = useId();
  const themes = [
    { value: "system", label: t("settings.appearance.system"), icon: Monitor },
    { value: "light", label: t("settings.values.light"), icon: Sun },
    { value: "dark", label: t("settings.values.dark"), icon: Moon },
  ] as const;
  const editHelp = { summary: "summaryHelp", diff: "diffHelp", collapsed_diff: "collapsedHelp" } as const;

  return <div className="settings-stack appearance-page">
    <section>
      <SettingsSectionTitle>{t("settings.rows.theme")}</SettingsSectionTitle>
      <fieldset>
        <legend className="sr-only">{t("settings.rows.theme")}</legend>
        <div className="appearance-theme-grid">
          {themes.map(({ value, label, icon: Icon }) => <label key={value} className="appearance-theme-option">
            <input className="appearance-theme-input" type="radio" name={themeId} value={value}
              checked={themePreference === value} onChange={() => onChangeTheme(value)} />
            <span className="appearance-theme-card">
              <span className="appearance-theme-miniature" data-mode={value} aria-hidden>
                <span className="appearance-mini-sidebar"><span /><span /><span /></span>
                <span className="appearance-mini-main"><span /><span /><span /><span /></span>
              </span>
              <span className="appearance-theme-label text-ui-label">
                <span className="flex min-w-0 items-center gap-1.5"><Icon className="h-3.5 w-3.5 shrink-0" aria-hidden /><span>{label}</span></span>
                <Check className="appearance-theme-check h-3.5 w-3.5 shrink-0" aria-hidden />
              </span>
            </span>
          </label>)}
        </div>
      </fieldset>
    </section>

    <AccentSection />

    <section>
      <SettingsSectionTitle>{t("settings.appearance.reading")}</SettingsSectionTitle>
      <ReadingSettings preferences={localPrefs} onChange={onChangeLocalPrefs} />
      <div className="mt-2">
        <SettingsGroup>
          <SettingsRow title={t("settings.rows.codeWrap")} description={t("settings.help.codeWrap")}>
            <ToggleButton checked={localPrefs.codeWrap}
              onChange={(codeWrap) => onChangeLocalPrefs((previous) => ({ ...previous, codeWrap }))}
              ariaLabel={t("settings.rows.codeWrap")}
              label={t(localPrefs.codeWrap ? "settings.values.on" : "settings.values.off")} />
          </SettingsRow>
        </SettingsGroup>
      </div>
    </section>

    <section>
      <SettingsSectionTitle>
        <SettingsHint description={t("settings.appearance.processHelp")}>{t("settings.appearance.process")}</SettingsHint>
      </SettingsSectionTitle>
      <SettingsGroup>
        <SettingsRow title={t("settings.rows.activityMode")}
          description={t(`settings.appearance.${localPrefs.activityMode === "auto" ? "autoHelp" : "expandedHelp"}`)}>
          <SegmentedControl<LocalActivityMode> value={localPrefs.activityMode}
            ariaLabel={t("settings.rows.activityMode")}
            options={[{ value: "auto", label: t("settings.values.auto") }, { value: "expanded", label: t("settings.values.expanded") }]}
            onChange={(activityMode) => onChangeLocalPrefs((previous) => ({ ...previous, activityMode }))} />
        </SettingsRow>
        <div className="settings-group-divider">
          <SettingsRow title={t("settings.rows.fileEditDisplay")}
            description={t(`settings.appearance.${editHelp[localPrefs.fileEditDisplayMode]}`)}>
            <SegmentedControl<FileEditDisplayMode> value={localPrefs.fileEditDisplayMode}
              ariaLabel={t("settings.rows.fileEditDisplay")}
              options={[
                { value: "summary", label: t("settings.values.summary") },
                { value: "diff", label: t("settings.values.diff") },
                { value: "collapsed_diff", label: t("settings.values.collapsedDiff") },
              ]}
              onChange={(fileEditDisplayMode) => onChangeLocalPrefs((previous) => ({ ...previous, fileEditDisplayMode }))} />
          </SettingsRow>
        </div>
      </SettingsGroup>
    </section>

    <section>
      <SettingsSectionTitle>{t("settings.sections.interface")}</SettingsSectionTitle>
      <SettingsGroup>
        <SettingsRow title={t("settings.rows.language")}><LanguageSwitcher /></SettingsRow>
        <SettingsRow title={t("settings.rows.brandLogos")} description={t("settings.legal.thirdPartyBrands")}>
          <ToggleButton checked={localPrefs.brandLogos}
            onChange={(brandLogos) => onChangeLocalPrefs((previous) => ({ ...previous, brandLogos }))}
            ariaLabel={t("settings.rows.brandLogos")}
            label={t(localPrefs.brandLogos ? "settings.values.on" : "settings.values.off")} />
        </SettingsRow>
      </SettingsGroup>
    </section>
  </div>;
}

const SWATCH: Record<Accent, string> = {
  neutral: "bg-zinc-800 dark:bg-zinc-200", blue: "bg-blue-600 dark:bg-blue-400", green: "bg-emerald-700 dark:bg-emerald-400",
  amber: "bg-amber-600 dark:bg-amber-400", rose: "bg-rose-600 dark:bg-rose-400", violet: "bg-violet-600 dark:bg-violet-400",
};

/** The accent colour: buttons that do the main thing, the selected tab, focus rings and what needs you. */
function AccentSection() {
  const { t } = useTranslation();
  const [accent, setAccent] = useAccent();
  const names: Record<Accent, string> = {
    neutral: t("settings.accent.neutral", { defaultValue: "Neutral" }), blue: t("settings.accent.blue", { defaultValue: "Blue" }),
    green: t("settings.accent.green", { defaultValue: "Green" }), amber: t("settings.accent.amber", { defaultValue: "Amber" }),
    rose: t("settings.accent.rose", { defaultValue: "Rose" }), violet: t("settings.accent.violet", { defaultValue: "Violet" }),
  };
  return <section>
    <SettingsSectionTitle>{t("settings.rows.accent", { defaultValue: "Accent colour" })}</SettingsSectionTitle>
    <SettingsGroup>
      <div className="settings-list-row flex flex-col gap-3 py-3">
        <p className="text-xs text-muted-foreground">
          {t("settings.help.accent", { defaultValue: "Used for the main button on a page, the selected tab, focus rings, and what needs you. In light and dark alike." })}
        </p>
        <div role="radiogroup" aria-label={t("settings.rows.accent", { defaultValue: "Accent colour" })} className="flex flex-wrap gap-2">
          {ACCENTS.map((value) => <button key={value} type="button" role="radio" aria-checked={accent === value} onClick={() => setAccent(value)}
            className={cn("flex items-center gap-2 rounded-full border px-3 py-1.5 text-[13px] transition-colors hover:bg-muted/60",
              accent === value && "border-foreground/40 bg-muted/60 font-medium")}>
            <span className={cn("h-3.5 w-3.5 rounded-full", SWATCH[value])} aria-hidden />{names[value]}
            {accent === value && <Check className="h-3.5 w-3.5" aria-hidden />}
          </button>)}
        </div>
      </div>
    </SettingsGroup>
  </section>;
}
