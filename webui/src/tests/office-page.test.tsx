import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OfficePage } from "@/components/office/OfficePage";
import { ClientProvider } from "@/providers/ClientProvider";
import type { BaboClient } from "@/lib/babo-client";
import type { OfficeView } from "@/lib/api";

const view: OfficeView = {
  projects: [{
    slug: "control-plane", title: "Control plane", project_lead: "mayor", status: "active", help_wanted: false,
    open_tickets: 3, lead: "dova-agent", crew: ["crew-2"], crew_recorded: true, agents: ["dova-agent", "crew-2"],
  }],
  agents: [
    { handle: "dova-agent", resident: "archivist", project: "control-plane", crew: "control-plane", role: "lead",
      status: "running", desired: "running", observed: "alive", wg_address: "10.9.0.5", last_activity_at: "",
      checkouts: [{ id: "c1", scope: "kimi", issued_at: "", expires_at: "" }], ended_reason: "", said: "" },
    { handle: "crew-2", resident: "inspector", project: "control-plane", crew: "control-plane", role: "crew",
      status: "frozen", desired: "frozen", observed: "frozen", wg_address: "10.9.0.6", last_activity_at: "",
      checkouts: [], ended_reason: "idle", said: "" },
  ],
  missing: [], drifted: [], unmanaged: [],
  manager: { name: "manager", available: true, said: "" },
  listener: "10.0.0.2:18790",
  desired: {},
};

const fetchOffice = vi.fn(async () => view);
const fetchOfficeOp = vi.fn(async (id: string) => ({ id, handle: "crew-2", action: "wake",
  state: "succeeded", said: "woke crew-2", observed: {} }));
const officeAgentAction = vi.fn(async (_client: unknown, handle: string, verb: string) => ({
  state: "pending", op: { id: "a1", handle, action: verb, state: "pending", said: "", observed: null },
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  fetchOffice: (...args: unknown[]) => fetchOffice(...(args as [])),
  fetchOfficeOp: (...args: unknown[]) => fetchOfficeOp(...(args as [string])),
  officeAgentAction: (...args: unknown[]) => officeAgentAction(...(args as [unknown, string, string])),
}));

const client = { requestMutation: vi.fn() } as unknown as BaboClient;

function renderPage() {
  return render(
    <ClientProvider client={client} token="test">
      <OfficePage onBackToChat={() => undefined} />
    </ClientProvider>,
  );
}

describe("OfficePage", () => {
  beforeEach(() => { fetchOffice.mockClear(); fetchOfficeOp.mockClear(); officeAgentAction.mockClear(); });
  afterEach(() => { vi.clearAllMocks(); });

  it("shows each project's lead and crew with the Manager's state", async () => {
    renderPage();
    expect(await screen.findByText("dova-agent")).toBeTruthy();
    expect(screen.getByText("Lead")).toBeTruthy();
    expect(screen.getByText("running")).toBeTruthy();
    expect(screen.getByText("frozen")).toBeTruthy();
    expect(screen.getByText("1 live checkout(s)")).toBeTruthy();
    expect(screen.getByText("stood down (idle)")).toBeTruthy();
  });

  it("asks the Manager to wake a frozen agent and shows its answer", async () => {
    renderPage();
    const row = (await screen.findByText("crew-2")).closest("li");
    expect(row).toBeTruthy();
    await userEvent.click(within(row as HTMLElement).getByText("Wake"));
    await waitFor(() => expect(officeAgentAction).toHaveBeenCalledWith(client, "crew-2", "wake", expect.any(String)));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("woke crew-2"));
  });

  it("says the Manager can't be read instead of showing agents as running", async () => {
    fetchOffice.mockResolvedValueOnce({ ...view,
      manager: { name: "manager", available: false, said: "can't reach the Manager at http://10.0.0.3:9200" } });
    renderPage();
    expect(await screen.findByText(/can't reach the Manager/)).toBeTruthy();
  });
});
