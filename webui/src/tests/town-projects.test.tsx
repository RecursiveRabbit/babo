import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectsView } from "@/components/town/ProjectsView";
import i18n from "@/i18n";

const mocks = vi.hoisted(() => ({ mutation: vi.fn(), fetch: vi.fn(), getToken: () => "token" }));
vi.mock("@/providers/ClientProvider", () => ({ useClient: () => ({ client: { requestMutation: mocks.mutation }, getToken: mocks.getToken }) }));

const ticket = (number: number, title: string, status: string, assignee = "", notes: string[] = []) => ({
  ref: `garden#${number}`, project: "garden", number, title, status, assignee, created_by: "mayor", created: "", updated: "",
  description: "", notes,
});
const board = {
  statuses: ["open", "doing", "blocked", "done"], project_statuses: ["active", "paused", "done"],
  projects: [{
    slug: "garden", title: "The Garden", lead: "mayor", status: "active", help_wanted: true, created: "", updated: "", description: "Grow it.",
    counts: { open: 1, doing: 1, blocked: 0, done: 0 },
    tickets: [ticket(1, "Water the beds", "open"), ticket(2, "Dig", "doing", "archivist", ["- 2026-11-04 10:00 archivist: took it"])],
  }],
};

beforeEach(async () => {
  await i18n.changeLanguage("en");
  mocks.fetch.mockReset();
  mocks.mutation.mockReset();
  mocks.fetch.mockImplementation(() => Promise.resolve(new Response(JSON.stringify(board), { status: 200, headers: { "content-type": "application/json" } })));
  mocks.mutation.mockResolvedValue({ message: "Updated garden#2.", projects: board });
  vi.stubGlobal("fetch", mocks.fetch);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("the Projects tab", () => {
  it("lists the projects, and a project's tickets in columns by status", async () => {
    render(<ProjectsView residents={["mayor", "archivist"]} onError={() => {}} />);
    const row = await screen.findByRole("button", { name: /The Garden/ });
    expect(row).toHaveTextContent("help wanted");
    expect(row).toHaveTextContent("1 open · 1 doing · 0 blocked · 0 done");
    fireEvent.click(row);
    expect(within(screen.getByRole("region", { name: "open" })).getByText("Water the beds")).toBeVisible();
    const doing = screen.getByRole("region", { name: "doing" });
    expect(within(doing).getByText("Dig")).toBeVisible();
    expect(within(doing).getByText("archivist")).toBeVisible();
  });

  it("changes a ticket, and asks why when it's blocked", async () => {
    render(<ProjectsView residents={["mayor", "archivist"]} onError={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /The Garden/ }));
    const card = screen.getByRole("article", { name: "garden#2" });
    fireEvent.click(within(card).getByRole("button", { name: /Dig/ }));
    expect(within(card).getByText("2026-11-04 10:00 archivist: took it")).toBeVisible();
    fireEvent.change(within(card).getByRole("combobox", { name: "Status" }), { target: { value: "blocked" } });
    const save = within(card).getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    fireEvent.change(within(card).getByRole("textbox", { name: "A note" }), { target: { value: "No water." } });
    fireEvent.click(save);
    await waitFor(() => expect(mocks.mutation).toHaveBeenCalledWith("town.projects",
      { action: "update_ticket", ticket: "garden#2", note: "No water.", status: "blocked" }, expect.any(Number)));
    expect(await screen.findByRole("status")).toHaveTextContent("Updated garden#2.");
  });

  it("starts a project and adds a ticket", async () => {
    mocks.mutation.mockResolvedValue({ message: "Started paper.", projects: board });
    render(<ProjectsView residents={["mayor", "archivist"]} onError={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "New project" }));
    const form = screen.getByRole("form", { name: "New project" });
    fireEvent.change(within(form).getByRole("textbox", { name: "Title" }), { target: { value: "Paper" } });
    fireEvent.click(within(form).getByRole("checkbox"));
    fireEvent.click(within(form).getByRole("button", { name: "Start it" }));
    await waitFor(() => expect(mocks.mutation).toHaveBeenCalledWith("town.projects",
      { action: "new_project", title: "Paper", description: "", help_wanted: true }, expect.any(Number)));
    fireEvent.click(screen.getByRole("button", { name: /The Garden/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "A new ticket" }), { target: { value: "Fence" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(mocks.mutation).toHaveBeenCalledWith("town.projects",
      { action: "new_ticket", project: "garden", title: "Fence" }, expect.any(Number)));
  });
});
