// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import * as api from "./api";
import type { ControlRoom, Customer } from "./types";

vi.mock("./api", () => ({
  archiveCustomer: vi.fn(),
  changePassword: vi.fn(),
  createCustomer: vi.fn(),
  createCustomerContact: vi.fn(),
  createScheduleAvailabilityRequest: vi.fn(),
  deleteCustomerContact: vi.fn(),
  getCustomer: vi.fn(),
  getCustomerHistory: vi.fn(),
  getCustomerObjects: vi.fn(),
  getCustomers: vi.fn(),
  getDashboard: vi.fn(),
  getCustomerPortalMe: vi.fn(),
  getCustomerPortalInvoices: vi.fn(),
  getCustomerPortalDocuments: vi.fn(),
  getCustomerPortalRequests: vi.fn(),
  downloadCustomerPortalInvoice: vi.fn(),
  getControlRoom: vi.fn(),
  getEmployees: vi.fn(),
  getEmployeeAvailability: vi.fn(),
  getObjects: vi.fn(),
  getNotifications: vi.fn(),
  getSession: vi.fn(),
  getUserSessions: vi.fn(),
  getUserSessionsForAdmin: vi.fn(),
  getMFAStatus: vi.fn(),
  getUsers: vi.fn(),
  getScheduleSettings: vi.fn(),
  getScheduleAvailabilityRequests: vi.fn(),
  getScheduleShifts: vi.fn(),
  replaceScheduleShiftEmployee: vi.fn(),
  getTimeEntries: vi.fn(),
  getTimeReport: vi.fn(),
  startTimeEntry: vi.fn(),
  getTimeCorrections: vi.fn(),
  getMissingShifts: vi.fn(),
  getTasks: vi.fn(),
  getTask: vi.fn(),
  getTaskAssignees: vi.fn(),
  getTaskLocations: vi.fn(),
  createTask: vi.fn(),
  createTaskComment: vi.fn(),
  updateTask: vi.fn(),
  login: vi.fn(),
  markNotificationRead: vi.fn(),
  revokeUserSession: vi.fn(),
  resetUserPassword: vi.fn(),
  startMFASetup: vi.fn(),
  enableMFA: vi.fn(),
  disableMFA: vi.fn(),
  logout: vi.fn(),
  reactivateCustomer: vi.fn(),
  updateCustomer: vi.fn(),
  updateCustomerContact: vi.fn(),
  updateEmployeeAvailability: vi.fn(),
  updateScheduleAvailabilityRequest: vi.fn(),
}));

const customer: Customer = {
  id: "customer-1",
  customer_number: "K-CUSTOMER1",
  company_name: "Beispiel GmbH",
  status: "active",
  contract_status: "none",
  email: null,
  phone: null,
  legal_form: null,
  website: null,
  vat_number: null,
  tax_number: null,
  internal_notes: null,
  archived_at: null,
  business_address: null,
  billing_address: null,
  contacts: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("Kundenformulare", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getSession).mockResolvedValue({
      user: {
        id: "user-1",
        username: "test",
        email: "test@example.de",
        full_name: "Testkonto",
        is_active: true,
        roles: [],
        permissions: ["customers.read", "customers.create"],
      },
    });

    vi.mocked(api.getCustomers).mockResolvedValue({
      items: [],
      total: 0,
      limit: 25,
      offset: 0,
    });
    vi.mocked(api.createCustomer).mockResolvedValue(customer);
    vi.mocked(api.getCustomer).mockResolvedValue(customer);
    vi.mocked(api.getCustomerHistory).mockResolvedValue([]);
  });

  it("öffnet die Leitstelle automatisch für berechtigte Rollen", async () => {
    vi.mocked(api.getSession).mockResolvedValue({
      user: {
        id: "control-room-user",
        username: "leitstelle",
        email: "leitstelle@example.de",
        full_name: "Leitstellenzugriff",
        is_active: true,
        roles: ["operations"],
        permissions: ["control_room.read", "objects.read"],
      },
    });

    const controlRoom: ControlRoom = {
      generated_at: "2026-11-09T06:00:00Z",
      range_start: "2026-11-02",
      range_end: "2026-12-09",
      counts: { active_objects: 0 },
      objects: [],
    };
    vi.mocked(api.getControlRoom).mockResolvedValue(controlRoom);
    render(<App />);

    expect(await screen.findByRole("button", { name: "Leitstelle" })).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "Leitstelle" })).toBeTruthy();
    expect(await screen.findByText("Keine aktiven, zugänglichen Objekte.")).toBeTruthy();
  });

  it("öffnet für Kundenportal-Konten ausschließlich die Kundenansicht", async () => {
    vi.mocked(api.getSession).mockResolvedValue({
      user: {
        id: "portal-user",
        username: "portal",
        email: "portal@example.com",
        full_name: "Portal-Konto",
        is_active: true,
        roles: ["customer_portal"],
        permissions: ["customer_portal.access"],
      },
    });
    vi.mocked(api.getCustomerPortalMe).mockResolvedValue({
      contact: {
        id: "contact-1",
        first_name: "Kunden",
        last_name: "Kontakt",
        responsibility: null,
        email: null,
        phone: null,
      },
      customer: {
        customer_number: "K-1",
        company_name: "Beispiel GmbH",
        email: null,
        phone: null,
        legal_form: null,
        website: null,
        business_address: null,
        billing_address: null,
      },
      objects: [],
    });
    vi.mocked(api.getCustomerPortalInvoices).mockResolvedValue([]);
    vi.mocked(api.getCustomerPortalDocuments).mockResolvedValue([]);
    vi.mocked(api.getCustomerPortalRequests).mockResolvedValue([]);
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Willkommen, Kunden." })).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "Beispiel GmbH" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Kunden" })).toBeNull();
    expect(api.getCustomers).not.toHaveBeenCalled();
  });

  it("bietet berechtigten Nutzern das zentrale Aufgabenmodul in der Navigation an", async () => {
    vi.mocked(api.getSession).mockResolvedValue({
      user: {
        id: "task-user",
        username: "aufgaben",
        email: "aufgaben@example.de",
        full_name: "Aufgabenbearbeitung",
        is_active: true,
        roles: ["employee"],
        permissions: ["tasks.read_own", "tasks.create", "tasks.update_own"],
      },
    });
    vi.mocked(api.getTasks).mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 });
    vi.mocked(api.getTaskLocations).mockResolvedValue({ customers: [], objects: [] });
    render(<App />);

    expect(await screen.findByRole("button", { name: "Aufgaben" })).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "Aufgaben" })).toBeTruthy();
    expect(await screen.findByText("Keine Aufgaben gefunden.")).toBeTruthy();
  });

  it("bietet berechtigten Nutzern den In-App-Posteingang an", async () => {
    vi.mocked(api.getSession).mockResolvedValue({
      user: {
        id: "notification-user",
        username: "benachrichtigungen",
        email: "benachrichtigungen@example.com",
        full_name: "Benachrichtigungszugriff",
        is_active: true,
        roles: ["employee"],
        permissions: ["notifications.read_own", "tasks.read_own"],
      },
    });
    vi.mocked(api.getNotifications).mockResolvedValue({
      items: [],
      total: 0,
      unread_count: 0,
      limit: 25,
      offset: 0,
    });
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Benachrichtigungen" }));
    expect(await screen.findByRole("heading", { name: "Benachrichtigungen" })).toBeTruthy();
    expect(await screen.findByText("Keine Benachrichtigungen vorhanden.")).toBeTruthy();
  });

  it("sendet den MFA-Code beim Anmelden an den Server", async () => {
    vi.mocked(api.getSession).mockRejectedValueOnce(new Error("Nicht angemeldet"));
    vi.mocked(api.login).mockResolvedValue({
      user: {
        id: "mfa-user",
        username: "test",
        email: "test@example.de",
        full_name: "Testkonto",
        is_active: true,
        roles: [],
        permissions: [],
      },
    });
    render(<App />);

    await screen.findByRole("heading", { name: "Anmelden" });
    fireEvent.change(screen.getByLabelText("Benutzername"), { target: { value: "test" } });
    fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: "test-passwort" } });
    fireEvent.change(screen.getByLabelText(/MFA-Code/), { target: { value: "123456" } });
    fireEvent.submit(screen.getByLabelText(/MFA-Code/).closest("form")!);

    await waitFor(() => {
      expect(api.login).toHaveBeenCalledWith("test", "test-passwort", { mfa_code: "123456" });
    });
  });

  it("sendet Website und Vertragsstatus beim Anlegen", async () => {
    render(<App />);

    await screen.findByRole("heading", { name: "Kunde hinzufügen" });
    fireEvent.change(screen.getByPlaceholderText("Muster GmbH"), {
      target: { value: "Beispiel GmbH" },
    });
    fireEvent.change(screen.getByLabelText("Website"), {
      target: { value: "https://beispiel.de" },
    });
    const form = screen.getByPlaceholderText("Muster GmbH").closest("form")!;
    fireEvent.change(form.querySelector('select[name="contract_status"]')!, {
      target: { value: "draft" },
    });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(api.createCustomer).toHaveBeenCalledWith(
        expect.objectContaining({
          website: "https://beispiel.de",
          contract_status: "draft",
        }),
      );
    });
  });

  it("zeigt Validierungsfehler der API im Formular an", async () => {
    vi.mocked(api.createCustomer).mockRejectedValueOnce(
      new Error("Website muss eine HTTP- oder HTTPS-Adresse sein."),
    );
    render(<App />);

    await screen.findByRole("heading", { name: "Kunde hinzufügen" });
    fireEvent.change(screen.getByPlaceholderText("Muster GmbH"), {
      target: { value: "Beispiel GmbH" },
    });
    fireEvent.submit(screen.getByText("Kunden speichern").closest("form")!);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Website muss eine HTTP- oder HTTPS-Adresse sein.",
    );
  });

  it("zeigt berechtigten Nutzern den Dienstplan mit Zeit und Schichtstatus", async () => {
    vi.mocked(api.getSession).mockResolvedValue({
      user: {
        id: "schedule-reader",
        username: "planleser",
        email: "planleser@example.de",
        full_name: "Planleser",
        is_active: true,
        roles: ["employee"],
        permissions: ["scheduling.read"],
      },
    });
    vi.mocked(api.getScheduleSettings).mockResolvedValue({
      time_zone: "Europe/Berlin",
      minimum_rest_hours: 11,
      updated_at: "2026-01-01T00:00:00Z",
    });
    vi.mocked(api.getScheduleShifts).mockResolvedValue([{
      id: "shift-1",
      employee_id: "employee-1",
      employee_number: "P-1001",
      employee_name: "Testperson",
      object_id: "object-1",
      object_code: "OBJ-001",
      object_name: "Testobjekt",
      starts_at: "2026-12-01T08:00:00Z",
      ends_at: "2026-12-01T16:00:00Z",
      time_zone: "Europe/Berlin",
      break_minutes: 30,
      required_qualification: "Erste Hilfe",
      status: "published",
      created_by_id: "manager-1",
      created_at: "2026-11-01T00:00:00Z",
      updated_at: "2026-11-01T00:00:00Z",
    }]);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Dienstplanung" })).toBeTruthy();
    expect(await screen.findByText("Testperson")).toBeTruthy();
    expect(screen.getByText("Veröffentlicht")).toBeTruthy();
    expect(screen.getByRole("option", { name: "Monat" })).toBeTruthy();
    expect(api.getScheduleShifts).toHaveBeenCalled();
  });

  it("pflegt regelmäßige Verfügbarkeit und trägt eine geprüfte Vertretung ein", async () => {
    const shift = {
      id: "shift-1",
      employee_id: "employee-1",
      employee_number: "P-1001",
      employee_name: "Testperson",
      object_id: "object-1",
      object_code: "OBJ-001",
      object_name: "Testobjekt",
      starts_at: "2026-12-01T08:00:00Z",
      ends_at: "2026-12-01T16:00:00Z",
      time_zone: "Europe/Berlin",
      break_minutes: 30,
      required_qualification: null,
      status: "published" as const,
      created_by_id: "manager-1",
      created_at: "2026-11-01T00:00:00Z",
      updated_at: "2026-11-01T00:00:00Z",
    };
    vi.mocked(api.getSession).mockResolvedValue({
      user: {
        id: "schedule-manager",
        username: "einsatzleitung",
        email: "einsatzleitung@example.de",
        full_name: "Einsatzleitung",
        is_active: true,
        roles: ["operations"],
        permissions: [
          "scheduling.read",
          "scheduling.manage",
          "scheduling.availability.request",
          "employees.read",
          "objects.read",
        ],
      },
    });
    vi.mocked(api.getScheduleSettings).mockResolvedValue({
      time_zone: "Europe/Berlin",
      minimum_rest_hours: 11,
      updated_at: "2026-01-01T00:00:00Z",
    });
    vi.mocked(api.getScheduleShifts).mockResolvedValue([shift]);
    vi.mocked(api.getEmployees).mockResolvedValue({
      items: [
        {
          id: "employee-1",
          employee_number: "P-1001",
          user_id: "user-1",
          full_name: "Testperson",
          email: null,
          phone: null,
          job_title: null,
          employment_status: "active",
          hired_on: "2020-01-01",
          ended_on: null,
          contract_type: null,
          weekly_hours: null,
          assigned_objects: [],
          archived_at: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
        {
          id: "employee-2",
          employee_number: "P-1002",
          user_id: "user-2",
          full_name: "Vertretung",
          email: null,
          phone: null,
          job_title: null,
          employment_status: "active",
          hired_on: "2020-01-01",
          ended_on: null,
          contract_type: null,
          weekly_hours: null,
          assigned_objects: [],
          archived_at: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
      total: 2,
      limit: 100,
      offset: 0,
    });
    vi.mocked(api.getObjects).mockResolvedValue({
      items: [{
        id: "object-1",
        code: "OBJ-001",
        name: "Testobjekt",
      } as Awaited<ReturnType<typeof api.getObjects>>["items"][number]],
      total: 1,
      limit: 100,
      offset: 0,
    });
    vi.mocked(api.getEmployeeAvailability).mockResolvedValue([]);
    vi.mocked(api.getScheduleAvailabilityRequests).mockResolvedValue([]);
    vi.mocked(api.updateEmployeeAvailability).mockResolvedValue([]);
    vi.mocked(api.replaceScheduleShiftEmployee).mockResolvedValue({
      ...shift,
      employee_id: "employee-2",
      employee_name: "Vertretung",
      employee_number: "P-1002",
    });

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Dienstplanung" }));
    await screen.findByRole("heading", { name: "Regelmäßige Zeitfenster" });
    fireEvent.click(screen.getByRole("button", { name: "Zeitfenster hinzufügen" }));
    fireEvent.click(screen.getByRole("button", { name: "Verfügbarkeit speichern" }));
    await waitFor(() => {
      expect(api.updateEmployeeAvailability).toHaveBeenCalledWith("employee-1", [
        { weekday: 0, starts_at: "09:00", ends_at: "17:00" },
      ]);
    });

    fireEvent.click(screen.getByRole("button", { name: "Vertretung" }));
    fireEvent.change(screen.getByLabelText("Vertretende Person"), {
      target: { value: "employee-2" },
    });
    fireEvent.change(screen.getByLabelText("Grundkategorie der Vertretung"), {
      target: { value: "short_notice" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Vertretung prüfen und speichern" }));
    await waitFor(() => {
      expect(api.replaceScheduleShiftEmployee).toHaveBeenCalledWith(
        "shift-1",
        "employee-2",
        "short_notice",
      );
    });
  });

  it("ermöglicht Mitarbeitenden, eigene Dienstwünsche einzureichen", async () => {
    vi.mocked(api.getSession).mockResolvedValue({
      user: {
        id: "employee-user",
        username: "mitarbeiter",
        email: "mitarbeiter@example.de",
        full_name: "Mitarbeiter",
        is_active: true,
        roles: ["employee"],
        permissions: ["scheduling.read", "scheduling.availability.request"],
      },
    });
    vi.mocked(api.getScheduleSettings).mockResolvedValue({
      time_zone: "Europe/Berlin",
      minimum_rest_hours: 11,
      updated_at: "2026-01-01T00:00:00Z",
    });
    vi.mocked(api.getScheduleShifts).mockResolvedValue([]);
    vi.mocked(api.getScheduleAvailabilityRequests).mockResolvedValue([]);
    vi.mocked(api.createScheduleAvailabilityRequest).mockResolvedValue({} as Awaited<
      ReturnType<typeof api.createScheduleAvailabilityRequest>
    >);

    render(<App />);

    await screen.findByRole("heading", { name: "Eigene Zeitwünsche" });
    const form = screen.getByRole("button", { name: "Zeitraum einreichen" }).closest("form")!;
    fireEvent.change(form.querySelector('input[name="starts_at_local"]')!, {
      target: { value: "2026-12-01T09:00" },
    });
    fireEvent.change(form.querySelector('input[name="ends_at_local"]')!, {
      target: { value: "2026-12-01T17:00" },
    });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(api.createScheduleAvailabilityRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: "preferred",
          starts_at_local: "2026-12-01T09:00",
          ends_at_local: "2026-12-01T17:00",
        }),
      );
    });
    expect(api.createScheduleAvailabilityRequest).not.toHaveBeenCalledWith(
      expect.objectContaining({ employee_id: expect.any(String) }),
    );
  });

  it("zeigt Mitarbeitenden die Zeiterfassung und startet eine Buchung", async () => {
    vi.mocked(api.getSession).mockResolvedValue({
      user: {
        id: "employee-user",
        username: "mitarbeiter",
        email: "mitarbeiter@example.de",
        full_name: "Mitarbeiter",
        is_active: true,
        roles: ["employee"],
        permissions: ["time_tracking.read_own", "time_tracking.create"],
      },
    });
    vi.mocked(api.getTimeEntries).mockResolvedValue([]);
    vi.mocked(api.getTimeReport).mockResolvedValue({
      from_date: "2026-11-01",
      to_date: "2026-11-08",
      time_zone: "Europe/Berlin",
      group_by: "employee",
      entry_count: 0,
      actual_work_seconds: 0,
      actual_break_seconds: 0,
      planned_work_seconds: 0,
      difference_seconds: 0,
      overtime_seconds: 0,
      pending_count: 0,
      groups: [],
      items: [],
    });
    vi.mocked(api.startTimeEntry).mockResolvedValue({} as Awaited<ReturnType<typeof api.startTimeEntry>>);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Zeiterfassung" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Arbeitszeit starten" }));
    await waitFor(() => expect(api.startTimeEntry).toHaveBeenCalledWith({}));
  });
});
