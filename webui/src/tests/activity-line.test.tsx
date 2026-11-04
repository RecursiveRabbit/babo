import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ActivityLine } from "@/components/town/ActivityLine";
import i18n from "@/i18n";

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), getToken: () => "token" }));
vi.mock("@/providers/ClientProvider", () => ({ useClient: () => ({ client: {}, getToken: mocks.getToken }) }));

const entry = (key: string, status: string, extra: Record<string, unknown> = {}) => ({
  key, kind: "round", label: "The night round", status, detail: "", started: new Date(Date.now() - 12_000).toISOString(),
  finished: status === "done" || status === "failed" ? new Date().toISOString() : "", resident: "", session: "",
  active: status === "waiting" || status === "running", ...extra,
});
const respond = (activity: unknown[]) => mocks.fetch.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ activity }),
  { status: 200, headers: { "content-type": "application/json" } })));

beforeEach(async () => { await i18n.changeLanguage("en"); mocks.fetch.mockReset(); vi.stubGlobal("fetch", mocks.fetch); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("activity beside the button that asked for it", () => {
  it("shows a round running, with how long it has been going", async () => {
    respond([entry("round:night", "running", { detail: "run by hand" })]);
    render(<ActivityLine activityKey="round:night" />);
    const line = await screen.findByRole("status");
    expect(line).toHaveTextContent(/Working on it · 1\d s: The night round · run by hand/);
    expect(line).toHaveAttribute("data-status", "running");
  });

  it("says when it's done, and why it didn't go through", async () => {
    respond([entry("round:night", "done", { detail: "2 step(s) done" }), entry("rehearsal:night", "failed", { detail: "step 1: no model" })]);
    render(<><ActivityLine activityKey="round:night" /><ActivityLine activityKey="rehearsal:night" /></>);
    expect(await screen.findByText(/2 step\(s\) done/)).toBeVisible();
    expect(screen.getByText("Didn't go through")).toBeVisible();
    expect(screen.getByText(/step 1: no model/)).toBeVisible();
  });

  it("shows nothing for something that isn't happening, or for an older Babo", async () => {
    mocks.fetch.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ rounds: [] }),
      { status: 200, headers: { "content-type": "application/json" } })));
    const { container } = render(<ActivityLine activityKey="round:night" />);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(container).toBeEmptyDOMElement();
  });
});
