// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import IncidentManagement from "./IncidentManagement";
import * as api from "./api";
import type { AuthUser, IncidentDetail, IncidentItem } from "./types";

vi.mock("./api", () => ({
  addIncidentPerson: vi.fn(),
  createIncident: vi.fn(),
  createIncidentMeasure: vi.fn(),
  downloadIncidentAttachment: vi.fn(),
  getIncident: vi.fn(),
  getIncidentChoices: vi.fn(),
  getIncidents: vi.fn(),
  updateIncident: vi.fn(),
  updateIncidentMeasure: vi.fn(),
  updateIncidentSensitiveDetails: vi.fn(),
  updateIncidentStatus: vi.fn(),
  uploadIncidentAttachment: vi.fn(),
}));

const incident: IncidentItem = {
  id: "incident-1",
  title: "Testvorfall",
  report: "Synthetische Kurzmeldung",
  incident_type: "incident",
  severity: "medium",
  object_id: "object-1",
  object_name: "Testobjekt",
  status: "reported",
  due_at: null,
  assigned_to_id: "user-1",
  assigned_to_name: "Testkonto",
  owks_event_id: null,
  created_by_id: "user-1",
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

const detail: IncidentDetail = {
  ...incident,
  sensitive_details: null,
  people: [],
  attachments: [],
  measures: [],
  history: [{
    id: "history-1",
    actor_id: "user-1",
    action: "status_changed",
    changes: { from: "reported", to: "investigating" },
    created_at: incident.created_at,
  }],
};

const user: AuthUser = {
  id: "user-1",
  username: "test",
  email: "test@example.test",
  full_name: "Testkonto",
  is_active: true,
  roles: ["employee"],
  permissions: ["incidents.read", "incidents.create", "incidents.update"],
};

describe("Vorfallmanagement", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getIncidents).mockResolvedValue({
      items: [incident],
      total: 1,
      limit: 25,
      offset: 0,
    });
    vi.mocked(api.getIncidentChoices).mockResolvedValue({
      objects: [{ id: "object-1", name: "Testobjekt", code: "INC-TEST" }],
      assignees: [{ id: "user-1", full_name: "Testkonto" }],
      linked_owks_event_ids: [],
    });
    vi.mocked(api.getIncident).mockResolvedValue(detail);
    vi.mocked(api.createIncident).mockResolvedValue(incident);
    vi.mocked(api.updateIncidentStatus).mockResolvedValue({
      ...incident,
      status: "investigating",
    });
  });

  it("zeigt Liste, Details, Verlauf und ermöglicht einen Statusübergang", async () => {
    render(<IncidentManagement user={user} />);

    fireEvent.click(await screen.findByRole("button", { name: /Testvorfall/ }));
    expect(await screen.findByText("Synthetische Kurzmeldung")).toBeTruthy();
    expect(screen.getByText("Status: Gemeldet → In Prüfung")).toBeTruthy();
    expect(screen.getByText(/gesonderte Berechtigung erforderlich/)).toBeTruthy();
    expect(
      within(screen.getByLabelText("Status ändern")).queryByRole("option", {
        name: "Abgeschlossen",
      }),
    ).toBeNull();

    fireEvent.change(screen.getByLabelText("Status ändern"), {
      target: { value: "investigating" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Status übernehmen" }));
    await waitFor(() => {
      expect(api.updateIncidentStatus).toHaveBeenCalledWith("incident-1", "investigating");
    });
  });

  it("sendet eine neue Meldung mit Objekt und Schweregrad an die API", async () => {
    render(<IncidentManagement user={user} />);
    await screen.findByRole("button", { name: /Testvorfall/ });
    fireEvent.change(screen.getByLabelText("Titel"), { target: { value: "Neue Testmeldung" } });
    fireEvent.change(screen.getByLabelText("Kurzmeldung"), {
      target: { value: "Eine synthetische Kurzmeldung." },
    });
    fireEvent.change(screen.getByLabelText("Objekt"), { target: { value: "object-1" } });
    fireEvent.submit(screen.getByRole("button", { name: "Vorfall melden" }).closest("form")!);

    await waitFor(() => {
      expect(api.createIncident).toHaveBeenCalledWith(expect.objectContaining({
        title: "Neue Testmeldung",
        report: "Eine synthetische Kurzmeldung.",
        object_id: "object-1",
        incident_type: "incident",
        severity: "medium",
      }));
    });
  });

  it("zeigt einen leeren Listenstatus", async () => {
    vi.mocked(api.getIncidents).mockResolvedValue({
      items: [],
      total: 0,
      limit: 25,
      offset: 0,
    });
    render(<IncidentManagement user={user} />);
    expect(await screen.findByText("Keine Vorfälle vorhanden.")).toBeTruthy();
  });
});
