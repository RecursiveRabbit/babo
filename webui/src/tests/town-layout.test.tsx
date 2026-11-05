import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AttentionStrip, TownNav, TownSection } from "@/components/town/TownLayout";
import { AppearanceSettingsView } from "@/components/settings/overview/AppearanceSettingsView";
import i18n from "@/i18n";

beforeEach(async () => { await i18n.changeLanguage("en"); });
afterEach(() => { cleanup(); localStorage.clear(); delete document.documentElement.dataset.accent; });

describe("the Town page's layout", () => {
  it("groups its areas under labels, and a count shows beside what waits", () => {
    const onChange = vi.fn();
    render(<TownNav value="town" onChange={onChange} ariaLabel="Town sections" groups={[
      { label: "The town", items: [{ value: "town", label: "Residents" }, { value: "review", label: "Review", badge: 2 }] },
      { label: "Setup", items: [{ value: "settings", label: "Settings" }] },
    ]} />);
    const nav = screen.getByRole("navigation", { name: "Town sections" });
    expect(within(nav).getByText("The town")).toBeVisible();
    expect(within(nav).getByText("Setup")).toBeVisible();
    expect(screen.getByRole("tab", { name: "Residents" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "Review (2)" }));
    expect(onChange).toHaveBeenCalledWith("review");
  });

  it("shows what needs you as buttons, and nothing when nothing does", () => {
    const go = vi.fn();
    const { rerender } = render(<AttentionStrip label="Needs you" items={[{ key: "r", text: "2 decision(s) wait in Review", onClick: go }]} />);
    fireEvent.click(within(screen.getByRole("region", { name: "Needs you" })).getByRole("button", { name: "2 decision(s) wait in Review" }));
    expect(go).toHaveBeenCalled();
    rerender(<AttentionStrip label="Needs you" items={[]} />);
    expect(screen.queryByRole("region", { name: "Needs you" })).toBeNull();
  });

  it("puts each area's title, what it's for and its actions together", () => {
    render(<TownSection title="Upkeep" description="Babo's own work." actions={<button type="button">Catch up now</button>}><p>Waiting.</p></TownSection>);
    const section = screen.getByRole("region", { name: "Upkeep" });
    expect(within(section).getByRole("heading", { name: "Upkeep" })).toBeVisible();
    expect(within(section).getByText("Babo's own work.")).toBeVisible();
    expect(within(section).getByRole("button", { name: "Catch up now" })).toBeVisible();
  });
});

describe("the accent colour", () => {
  it("is chosen in Appearance, applied at once and remembered", () => {
    render(<AppearanceSettingsView themePreference="system" onChangeTheme={() => {}} localPrefs={{} as never} onChangeLocalPrefs={() => {}} />);
    const accents = screen.getByRole("radiogroup", { name: "Accent colour" });
    expect(within(accents).getByRole("radio", { name: "Neutral" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(within(accents).getByRole("radio", { name: "Blue" }));
    expect(document.documentElement.dataset.accent).toBe("blue");
    expect(localStorage.getItem("babo-webui.accent")).toBe("blue");
    fireEvent.click(within(accents).getByRole("radio", { name: "Neutral" }));
    expect(document.documentElement.dataset.accent).toBeUndefined();
  });
});
