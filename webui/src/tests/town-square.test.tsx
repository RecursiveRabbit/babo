import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SquareView } from "@/components/town/SquareView";
import i18n from "@/i18n";

const mocks = vi.hoisted(() => ({ mutation: vi.fn(), fetch: vi.fn(), getToken: () => "token" }));
vi.mock("@/providers/ClientProvider", () => ({ useClient: () => ({ client: { requestMutation: mocks.mutation }, getToken: mocks.getToken }) }));

const square = {
  kinds: ["question", "observation", "flag", "announcement"],
  threads: [
    { id: "2026-11-04-ladder", kind: "question", title: "Who has the ladder?", author: "archivist", text: "For the shelves.", status: "open",
      created: "2026-11-04T10:00:00", updated: "2026-11-04T11:00:00", closed_by: "",
      replies: [{ at: "2026-11-04T11:00:00", by: "inspector", text: "In the shed." }] },
    { id: "2026-11-01-power", kind: "announcement", title: "Power cut", author: "owner", text: "At noon.", status: "closed",
      created: "2026-11-01T09:00:00", updated: "2026-11-01T13:00:00", closed_by: "owner", replies: [] },
  ],
};

beforeEach(async () => {
  await i18n.changeLanguage("en");
  mocks.fetch.mockReset();
  mocks.mutation.mockReset();
  mocks.fetch.mockImplementation(() => Promise.resolve(new Response(JSON.stringify(square), { status: 200, headers: { "content-type": "application/json" } })));
  mocks.mutation.mockResolvedValue({ message: "Replied on 2026-11-04-ladder.", square });
  vi.stubGlobal("fetch", mocks.fetch);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("the Square tab", () => {
  it("shows the open threads, a thread's replies, and the closed ones when asked", async () => {
    render(<SquareView onError={() => {}} />);
    const thread = await screen.findByRole("article", { name: "Who has the ladder?" });
    expect(thread).toHaveTextContent("question");
    expect(thread).toHaveTextContent("1 reply ·");
    fireEvent.click(within(thread).getByRole("button", { name: /Who has the ladder/ }));
    expect(within(thread).getByText("In the shed.")).toBeVisible();
    expect(screen.queryByText("Power cut")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Closed threads (1)" }));
    expect(screen.getByText("Power cut")).toBeVisible();
  });

  it("replies to a thread and starts one", async () => {
    render(<SquareView onError={() => {}} />);
    const thread = await screen.findByRole("article", { name: "Who has the ladder?" });
    fireEvent.click(within(thread).getByRole("button", { name: /Who has the ladder/ }));
    fireEvent.change(within(thread).getByRole("textbox", { name: "Your reply" }), { target: { value: "Thanks!" } });
    fireEvent.click(within(thread).getByRole("button", { name: "Reply" }));
    await waitFor(() => expect(mocks.mutation).toHaveBeenCalledWith("town.square",
      { action: "reply", thread: "2026-11-04-ladder", text: "Thanks!" }, expect.any(Number)));
    expect(await screen.findByRole("status")).toHaveTextContent("Replied on 2026-11-04-ladder.");
    fireEvent.click(screen.getByRole("button", { name: "Start a thread" }));
    const form = screen.getByRole("form", { name: "Start a thread" });
    fireEvent.change(within(form).getByRole("combobox", { name: "Kind" }), { target: { value: "question" } });
    fireEvent.change(within(form).getByRole("textbox", { name: "Title" }), { target: { value: "Tea?" } });
    fireEvent.change(within(form).getByRole("textbox", { name: "What it's about" }), { target: { value: "Anyone?" } });
    fireEvent.click(within(form).getByRole("button", { name: "Post" }));
    await waitFor(() => expect(mocks.mutation).toHaveBeenCalledWith("town.square",
      { action: "post", kind: "question", title: "Tea?", text: "Anyone?" }, expect.any(Number)));
  });
});
