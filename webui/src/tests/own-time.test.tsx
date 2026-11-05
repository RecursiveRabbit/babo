import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OwnTimePanel } from "@/components/town/OwnTimePanel";
import i18n from "@/i18n";

const mocks = vi.hoisted(() => ({ mutation: vi.fn(), fetch: vi.fn(), getToken: () => "token" }));
vi.mock("@/providers/ClientProvider", () => ({ useClient: () => ({ client: { requestMutation: mocks.mutation }, getToken: mocks.getToken }) }));

const data = {
  every: "weekly", choices: ["daily", "weekly", "off"],
  residents: [
    { resident: "archivist", name: "Wren", office: "archivist", every: "weekly", own_setting: false, next: "2026-11-11T03:00",
      recent: [{ resident: "archivist", started: "2026-11-04T03:00:00", finished: "", status: "done", why: "", said: "Wrote to the inspector, then rested." }] },
    { resident: "inspector", name: "", office: "inspector", every: "off", own_setting: true, next: "", recent: [] },
  ],
};

beforeEach(async () => {
  await i18n.changeLanguage("en");
  mocks.mutation.mockReset().mockResolvedValue({ message: "inspector's own time starts within a minute, when the model is free.", own_time: data });
  mocks.fetch.mockReset().mockImplementation((url: string) => Promise.resolve(new Response(
    JSON.stringify(url.includes("/api/town/own-time") ? data : { activity: [] }), { status: 200, headers: { "content-type": "application/json" } })));
  vi.stubGlobal("fetch", mocks.fetch);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("own time, beside the rounds", () => {
  it("shows how often each resident has it, when it comes next, and what it did with the last one", async () => {
    render(<OwnTimePanel onNotice={() => {}} onError={() => {}} />);
    const panel = await screen.findByRole("region", { name: "Own time" });
    expect(within(panel).getByText("Wren")).toBeVisible();
    expect(within(panel).getByText("next: 2026-11-11 03:00")).toBeVisible();
    expect(within(panel).getByText("Wrote to the inspector, then rested.")).toBeVisible();
    expect(within(panel).getByRole("combobox", { name: "Own time for inspector" })).toHaveValue("off");
    expect(within(panel).getByRole("combobox", { name: "Own time for archivist" })).toHaveValue("town");
  });

  it("sets it for the town or one resident, and gives a resident its time now", async () => {
    const notices: string[] = [];
    render(<OwnTimePanel onNotice={(m) => notices.push(m)} onError={() => {}} />);
    const panel = await screen.findByRole("region", { name: "Own time" });
    fireEvent.click(within(panel).getByRole("button", { name: "Daily" }));
    await waitFor(() => expect(mocks.mutation).toHaveBeenCalledWith("town.own_time.set", { every: "daily" }, expect.any(Number)));
    fireEvent.change(within(panel).getByRole("combobox", { name: "Own time for archivist" }), { target: { value: "off" } });
    await waitFor(() => expect(mocks.mutation).toHaveBeenCalledWith("town.own_time.set", { every: "off", resident: "archivist" }, expect.any(Number)));
    fireEvent.click(within(panel).getAllByRole("button", { name: "Give it its time now" })[1]);
    await waitFor(() => expect(mocks.mutation).toHaveBeenCalledWith("town.own_time.now", { resident: "inspector" }, expect.any(Number)));
    expect(notices.at(-1)).toContain("starts within a minute");
  });
});
