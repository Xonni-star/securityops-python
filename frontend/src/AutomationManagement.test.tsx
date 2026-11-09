// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AutomationManagement from "./AutomationManagement";
import * as api from "./api";

vi.mock("./api", () => ({
  createAutomationRule: vi.fn(),
  deleteAutomationRule: vi.fn(),
  getAutomationDeadLetters: vi.fn(),
  getAutomationRules: vi.fn(),
  getAutomationRuns: vi.fn(),
  retryAutomationEvent: vi.fn(),
  retryAutomationRun: vi.fn(),
  updateAutomationRule: vi.fn(),
}));

const rule = {
  id: "rule-1",
  name: "Blockierte Aufgaben melden",
  description: "Testregel",
  trigger_type: "task.status_changed" as const,
  conditions: { status: "blocked" as const },
  action_type: "notify_event_recipients" as const,
  is_active: false,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

describe("Automatisierungen", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getAutomationRules).mockResolvedValue([rule]);
    vi.mocked(api.getAutomationRuns).mockResolvedValue({
      items: [],
      total: 0,
      limit: 25,
      offset: 0,
    });
    vi.mocked(api.getAutomationDeadLetters).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(api.createAutomationRule).mockResolvedValue(rule);
    vi.mocked(api.updateAutomationRule).mockResolvedValue({ ...rule, is_active: true });
  });

  it("zeigt begrenzte Trigger und aktiviert Regeln serverseitig", async () => {
    render(<AutomationManagement />);

    expect(await screen.findByText("Blockierte Aufgaben melden")).toBeTruthy();
    expect(screen.getByText(/Qualifikationsablauf/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Aktivieren" }));

    await waitFor(() => {
      expect(api.updateAutomationRule).toHaveBeenCalledWith("rule-1", { is_active: true });
    });
  });

  it("legt Regeln mit dem festen Ereignisempfänger-Auslöser an", async () => {
    vi.mocked(api.getAutomationRules).mockResolvedValue([]);
    render(<AutomationManagement />);

    fireEvent.change(await screen.findByLabelText("Regelname"), {
      target: { value: "Aufgabe prüfen" },
    });
    fireEvent.change(screen.getByLabelText("Bedingung: Aufgabenstatus"), {
      target: { value: "blocked" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Regel anlegen" }));

    await waitFor(() => {
      expect(api.createAutomationRule).toHaveBeenCalledWith({
        name: "Aufgabe prüfen",
        description: undefined,
        trigger_type: "task.assigned",
        conditions: { status: "blocked" },
      });
    });
  });

  it("bietet die manuelle Rechnungsfreigabe ohne Aufgabenbedingung an", async () => {
    vi.mocked(api.getAutomationRules).mockResolvedValue([]);
    render(<AutomationManagement />);

    fireEvent.change(await screen.findByLabelText("Regelname"), {
      target: { value: "Freigabehinweis" },
    });
    fireEvent.change(screen.getByLabelText("Auslöser"), {
      target: { value: "billing.invoice_approved" },
    });
    expect(screen.queryByLabelText("Bedingung: Aufgabenstatus")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Regel anlegen" }));

    await waitFor(() => {
      expect(api.createAutomationRule).toHaveBeenCalledWith({
        name: "Freigabehinweis",
        description: undefined,
        trigger_type: "billing.invoice_approved",
        conditions: {},
      });
    });
  });

  it("bietet bestätigte Schlüsselausgaben ohne Aufgabenbedingung an", async () => {
    vi.mocked(api.getAutomationRules).mockResolvedValue([]);
    render(<AutomationManagement />);

    fireEvent.change(await screen.findByLabelText("Regelname"), {
      target: { value: "Schlüsselausgabe melden" },
    });
    fireEvent.change(screen.getByLabelText("Auslöser"), {
      target: { value: "key.issued" },
    });
    expect(screen.queryByLabelText("Bedingung: Aufgabenstatus")).toBeNull();
    expect(screen.getByText(/Rückgabefrist/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Regel anlegen" }));

    await waitFor(() => {
      expect(api.createAutomationRule).toHaveBeenCalledWith({
        name: "Schlüsselausgabe melden",
        description: undefined,
        trigger_type: "key.issued",
        conditions: {},
      });
    });
  });
});
