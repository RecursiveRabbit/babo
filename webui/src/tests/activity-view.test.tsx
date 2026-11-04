import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ActivityView } from "@/components/town/ActivityView";
import i18n from "@/i18n";

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), getToken: () => "token" }));
vi.mock("@/providers/ClientProvider", () => ({ useClient: () => ({ client: {}, getToken: mocks.getToken }) }));

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } }));
const started = new Date(Date.now() - 75_000).toISOString();
const now = {
  activity: [
    { key: "round:night", kind: "round", label: "The night round", status: "running", detail: "step 2 of 3", started, finished: "", resident: "", session: "", active: true },
    { key: "upkeep", kind: "upkeep", label: "Upkeep", status: "failed", detail: "no model", started, finished: started, resident: "", session: "", active: false },
  ],
  sessions: [{ resident: "archivist", id: "s1", title: "Tidy the notes", kind: "work", state: "waiting", doing: "asking to run git" }],
  queue: { slots: 2, active: 1, waiting: 3 },
  errands: [{ id: "e1", resident: "inspector", task: "Check the links", status: "running" }],
  upkeep: { running: false, waiting: ["promotions"] },
};
const logs = (service: string) => ({ service, services: ["gateway", "queue", "upkeep"], entries: [
  { level: "INFO", text: `${service}: started` }, { level: "ERROR", text: `${service}: it broke\nTraceback` },
] });

beforeEach(async () => {
  await i18n.changeLanguage("en");
  mocks.fetch.mockReset();
  mocks.fetch.mockImplementation((url: string) => {
    if (url.includes("/api/town/now")) return json(now);
    const query = new URL(url, "http://x").searchParams;
    return json(logs(query.get("service") ?? "gateway"));
  });
  vi.stubGlobal("fetch", mocks.fetch);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("the Activity tab", () => {
  it("says what's happening right now", async () => {
    render(<ActivityView onError={() => {}} />);
    const right = await screen.findByRole("region", { name: "Right now" });
    expect(await within(right).findByText(/1 of 2 busy · 3 waiting/)).toBeVisible();
    expect(within(right).getByText("The night round")).toBeVisible();
    expect(within(right).getByText(/for 1 min/)).toBeVisible();
    expect(within(right).getByText("Tidy the notes")).toBeVisible();
    expect(within(right).getByText(/asking to run git/)).toBeVisible();
    expect(within(right).getByText(/Check the links/)).toBeVisible();
    expect(within(right).getByText(/promotions/)).toBeVisible();
    const finished = screen.getByRole("region", { name: "Just finished" });
    expect(within(finished).getByText(/no model/)).toBeVisible();
  });

  it("shows a service's log, and another when asked", async () => {
    render(<ActivityView onError={() => {}} />);
    const entries = await screen.findByLabelText("Log entries");
    expect(await within(entries).findByText(/gateway: it broke/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Model queue" }));
    expect(await within(screen.getByLabelText("Log entries")).findByText(/queue: started/)).toBeVisible();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "ERROR" } });
    await vi.waitFor(() => expect(mocks.fetch.mock.calls.some(([url]) => String(url).includes("level=ERROR"))).toBe(true));
  });
});
