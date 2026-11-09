// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TaskManagement from "./TaskManagement";
import * as api from "./api";
import type { AuthUser, TaskDetail, TaskItem } from "./types";

vi.mock("./api", () => ({
  createTask: vi.fn(),
  createTaskComment: vi.fn(),
  getTask: vi.fn(),
  getTaskAssignees: vi.fn(),
  getTaskLocations: vi.fn(),
  getTasks: vi.fn(),
  updateTask: vi.fn(),
}));

const user: AuthUser = {
  id: "user-1",
  username: "test",
  email: "test@example.de",
  full_name: "Testkonto",
  is_active: true,
  roles: ["employee"],
  permissions: ["tasks.read_own", "tasks.create", "tasks.update_own"],
};

const task: TaskItem = {
  id: "task-1",
  title: "Kontrollbericht prüfen",
  description: "Ergebnis dokumentieren",
  assigned_to_id: "user-1",
  assigned_to_name: "Testkonto",
  created_by_id: "user-1",
  created_by_name: "Testkonto",
  customer_id: null,
  customer_name: null,
  object_id: null,
  object_name: null,
  due_at: null,
  priority: "normal",
  status: "open",
  completion_evidence: null,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

const detail: TaskDetail = { ...task, comments: [], history: [] };

describe("Aufgabenverwaltung", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getTasks).mockResolvedValue({
      items: [task],
      total: 1,
      limit: 25,
      offset: 0,
    });
    vi.mocked(api.getTaskLocations).mockResolvedValue({ customers: [], objects: [] });
    vi.mocked(api.getTask).mockResolvedValue(detail);
    vi.mocked(api.createTask).mockResolvedValue(task);
  });

  it("zeigt Aufgaben, öffnet Details und legt eine neue Aufgabe an", async () => {
    render(<TaskManagement user={user} />);

    expect(await screen.findByText("Kontrollbericht prüfen")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Kontrollbericht prüfen/ }));
    expect(await screen.findByRole("heading", { name: "Kontrollbericht prüfen" })).toBeTruthy();
    expect(screen.getByText("Ergebnis dokumentieren", { selector: "p" })).toBeTruthy();

    const createForm = screen.getByRole("form", { name: "Aufgabe anlegen" });
    fireEvent.change(within(createForm).getByLabelText("Titel"), {
      target: { value: "Schließrunde prüfen" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Aufgabe speichern" }).closest("form")!);

    await waitFor(() => {
      expect(api.createTask).toHaveBeenCalledWith({
        title: "Schließrunde prüfen",
        description: undefined,
        priority: "normal",
        due_at: undefined,
        assigned_to_id: undefined,
        customer_id: undefined,
        object_id: undefined,
      });
    });
    expect(await screen.findByText("Aufgabe wurde angelegt.")).toBeTruthy();
  });

  it("weist Aufgaben ohne Einträge mit einem Leerzustand aus", async () => {
    vi.mocked(api.getTasks).mockResolvedValueOnce({ items: [], total: 0, limit: 25, offset: 0 });
    render(<TaskManagement user={user} />);
    expect(await screen.findByText("Keine Aufgaben gefunden.")).toBeTruthy();
  });
});
