// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ControlRoom from "./ControlRoom";
import { getControlRoom, getEmployees, getSession } from "./api";
import type { AuthUser, ControlRoom as ControlRoomData } from "./types";

vi.mock("./api", () => ({
  getControlRoom: vi.fn(),
  getEmployees: vi.fn(),
  getSession: vi.fn(),
}));

const user: AuthUser = {
  id: "operator-1",
  username: "leitstelle",
  email: "leitstelle@example.de",
  full_name: "Test Leitstelle",
  is_active: true,
  roles: ["operations"],
  permissions: ["control_room.read", "employees.read"],
};

const pastDue = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
const response: ControlRoomData = {
  generated_at: "2026-11-09T06:00:00Z",
  range_start: "2026-11-02",
  range_end: "2026-12-09",
  counts: {
    active_objects: 1,
    active_shifts: 0,
    open_tasks: 2,
    urgent_tasks: 1,
  },
  objects: [{ id: "object-1", code: "TEST-1", name: "Testobjekt" }],
  shifts: [],
  tasks: [
    {
      id: "task-1",
      title: "Überfällige Testaufgabe",
      object_id: "object-1",
      object_name: "Testobjekt",
      status: "open",
      priority: "normal",
      due_at: pastDue,
      assigned_to_name: "Testverantwortung",
      created_at: "2026-11-08T09:00:00Z",
    },
    {
      id: "task-2",
      title: "Andere Testaufgabe",
      object_id: "object-1",
      object_name: "Testobjekt",
      status: "in_progress",
      priority: "normal",
      due_at: "2026-12-01T10:00:00Z",
      assigned_to_name: "Testverantwortung",
      created_at: "2026-11-08T09:00:00Z",
    },
  ],
};

describe("Leitstelle", () => {
  afterEach(cleanup);

  it("zeigt Momentaufnahme, Statusfilter und lädt erneut mit Objekt- und Zeitfiltern", async () => {
    vi.mocked(getControlRoom).mockResolvedValue(response);
    vi.mocked(getSession).mockResolvedValue({ user });
    render(<ControlRoom />);

    expect(await screen.findByText("Überfällige Testaufgabe")).toBeTruthy();
    expect(screen.getAllByText(/Verantwortlich: Testverantwortung/)).toHaveLength(2);
    expect(screen.getByText(/Erstellt am .* UTC · Zeitraum .* \(UTC\)/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Status / Priorität"), { target: { value: "überfällig" } });
    expect(screen.getByText("Überfällige Testaufgabe")).toBeTruthy();
    expect(screen.queryByText("Andere Testaufgabe")).toBeNull();

    fireEvent.change(screen.getByLabelText("Objekt"), { target: { value: "object-1" } });
    await waitFor(() => {
      expect(getControlRoom).toHaveBeenLastCalledWith({
        object_id: "object-1",
        from_date: expect.any(String),
        to_date: expect.any(String),
      });
    });
  });

  it("zeigt Lade- und Fehlerzustände statt einer Erfolgskarte bei Fehlern", async () => {
    let rejectRequest: (reason: Error) => void = () => undefined;
    vi.mocked(getControlRoom).mockImplementation(() => new Promise((_resolve, reject) => {
      rejectRequest = reject;
    }));
    vi.mocked(getSession).mockResolvedValue({ user });
    render(<ControlRoom />);
    expect(screen.getByRole("status").textContent).toContain("werden geladen");
    rejectRequest(new Error("Leitstelle nicht erreichbar"));
    expect((await screen.findByRole("alert")).textContent).toContain("Leitstelle nicht erreichbar");
    expect(screen.queryByRole("region", { name: "Leitstellenkennzahlen" })).toBeNull();
    expect(await screen.findByRole("tab", { name: "Mitarbeiter suchen" })).toBeTruthy();
  });

  it("stellt berechtigte Leitstellenaktionen bereit und sucht Mitarbeiter über die Personal-API", async () => {
    vi.mocked(getControlRoom).mockResolvedValue(response);
    vi.mocked(getSession).mockResolvedValue({ user });
    vi.mocked(getEmployees).mockResolvedValue({
      items: [{
        id: "employee-1",
        employee_number: "P-TEST-1",
        user_id: "user-1",
        full_name: "Testmitarbeiter",
        email: null,
        phone: null,
        job_title: "Sicherheitskraft",
        employment_status: "active",
        hired_on: "2020-01-01",
        ended_on: null,
        contract_type: null,
        weekly_hours: null,
        assigned_objects: ["Testobjekt (TEST-1)"],
        archived_at: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      }],
      total: 1,
      limit: 25,
      offset: 0,
    });
    render(<ControlRoom />);

    fireEvent.click(await screen.findByRole("tab", { name: "Mitarbeiter suchen" }));
    fireEvent.change(screen.getByLabelText("Name oder Personalnummer"), {
      target: { value: "P-TEST" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Suchen" }));

    expect(await screen.findByText("Testmitarbeiter")).toBeTruthy();
    expect(getEmployees).toHaveBeenCalledWith({
      q: "P-TEST",
      status: "active",
      includeArchived: false,
      sortBy: "full_name",
      sortOrder: "asc",
      limit: 25,
      offset: 0,
    });
  });
});
