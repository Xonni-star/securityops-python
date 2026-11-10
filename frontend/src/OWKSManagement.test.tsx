// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import OWKSManagement from "./OWKSManagement";
import * as api from "./api";
import type { AuthUser, OWKSEvent } from "./types";

const qrScanner = vi.hoisted(() => ({
  callback: undefined as
    | ((result: { getText: () => string } | undefined, error: unknown, controls: { stop: () => void }) => void)
    | undefined,
  stop: vi.fn(),
}));

vi.mock("./api", () => ({
  createIncident: vi.fn(),
  createOWKSChallenge: vi.fn(),
  createOWKSControlPoint: vi.fn(),
  createOWKSEvent: vi.fn(),
  createOWKSShiftHandover: vi.fn(),
  confirmOWKSShiftHandover: vi.fn(),
  createOWKSRoute: vi.fn(),
  getOWKSControlPoints: vi.fn(),
  getOWKSAttachments: vi.fn(),
  getOWKSEvents: vi.fn(),
  getOWKSShiftHandoverContext: vi.fn(),
  getOWKSShiftHandovers: vi.fn(),
  getOWKSObjects: vi.fn(),
  getOWKSRoutes: vi.fn(),
  getIncidentChoices: vi.fn(),
  monitorOWKSRoute: vi.fn(),
  owksAttachmentUrl: vi.fn(),
  recordOWKSScan: vi.fn(),
  syncOWKSEvents: vi.fn(),
  updateOWKSEventStatus: vi.fn(),
  uploadOWKSAttachment: vi.fn(),
}));

vi.mock("@zxing/browser", () => ({
  BrowserMultiFormatReader: class {
    decodeFromVideoDevice(
      _deviceId: string | undefined,
      _video: HTMLVideoElement,
      callback: typeof qrScanner.callback,
    ) {
      qrScanner.callback = callback ?? undefined;
      return Promise.resolve({ stop: qrScanner.stop });
    }
  },
}));

const user: AuthUser = {
  id: "employee-1",
  username: "wache",
  email: "wache@example.de",
  full_name: "Testwache",
  is_active: true,
  roles: ["employee"],
  permissions: ["owks.read", "owks.write"],
};

describe("OWKS-NFC-Fallback", () => {
  afterEach(() => {
    cleanup();
    Reflect.deleteProperty(window, "NDEFReader");
    Reflect.deleteProperty(navigator, "mediaDevices");
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: false });
    qrScanner.callback = undefined;
    qrScanner.stop.mockClear();
  });

  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
    vi.mocked(api.getOWKSObjects).mockResolvedValue([
      { id: "object-1", code: "OBJ-1", name: "Testobjekt" },
    ]);
    vi.mocked(api.getOWKSEvents).mockResolvedValue([]);
    vi.mocked(api.getOWKSShiftHandovers).mockResolvedValue([]);
    vi.mocked(api.getOWKSShiftHandoverContext).mockResolvedValue({
      current_employee_id: null,
      shifts: [],
      recipients: [],
      source_items: [],
    });
    vi.mocked(api.getOWKSControlPoints).mockResolvedValue([]);
    vi.mocked(api.getOWKSRoutes).mockResolvedValue([]);
    vi.mocked(api.getIncidentChoices).mockResolvedValue({
      objects: [{ id: "object-1", code: "OBJ-1", name: "Testobjekt" }],
      assignees: [{ id: "employee-1", full_name: "Testwache" }],
      linked_owks_event_ids: [],
    });
    vi.mocked(api.createIncident).mockResolvedValue({} as never);
    vi.mocked(api.createOWKSChallenge).mockResolvedValue({
      id: "challenge-1",
      object_id: "object-1",
      expires_at: "2026-11-08T22:00:00Z",
    });
    vi.mocked(api.recordOWKSScan).mockResolvedValue({} as never);
  });

  it("weist ohne sichere Web-NFC-Unterstützung auf QR- und manuelle Eingabe hin", async () => {
    Reflect.deleteProperty(window, "NDEFReader");
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: false });
    render(<OWKSManagement user={user} />);

    expect(await screen.findByText(/Web-NFC ist in diesem Browser\/Gerät oder ohne sicheren Kontext/))
      .toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Kontrollanforderung starten" }));
    const cameraButton = await screen.findByRole("button", { name: "QR-Code mit Kamera scannen" });
    expect(cameraButton.hasAttribute("disabled")).toBe(true);
  });

  it("zeigt den NFC-Leser nur bei sicherem Kontext und vorhandener Web-NFC-API", async () => {
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn() },
    });
    Reflect.defineProperty(window, "NDEFReader", {
      configurable: true,
      value: class {
        scan = vi.fn();
        write = vi.fn();
        onreading = null;
        onreadingerror = null;
      },
    });
    render(<OWKSManagement user={user} />);

    await screen.findByRole("heading", { name: "Online-Wachbuch" });
    fireEvent.click(screen.getByRole("button", { name: "Kontrollanforderung starten" }));
    await screen.findByRole("button", { name: "NFC-Tag lesen" });
    expect(screen.getByRole("button", { name: "NFC-Tag lesen" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "QR-Code mit Kamera scannen" }).hasAttribute("disabled"))
      .toBe(false);
  });

  it("kennzeichnet statische Kontrollkennungen als physisch unbestätigt", async () => {
    const scanEvent: OWKSEvent = {
      id: "scan-1",
      object_id: "object-1",
      route_id: null,
      control_point_id: "point-1",
      corrects_event_id: null,
      employee_id: "employee-1",
      actor_id: "user-1",
      client_event_id: "scan-client-1",
      event_type: "control",
      severity: "info",
      title: "Kennung erkannt: Haupteingang",
      description: "Kennung am Kontrollpunkt abgeglichen.",
      occurred_at: "2026-11-08T20:00:00Z",
      sync_status: "synced",
      presence_verified: false,
      status: "open",
      created_at: "2026-11-08T20:00:00Z",
    };
    vi.mocked(api.getOWKSEvents).mockResolvedValue([scanEvent]);
    render(<OWKSManagement user={user} />);

    expect(await screen.findByText("Physische Anwesenheit nicht bestätigt")).toBeTruthy();
  });

  it("sendet einen Kamera-QR-Treffer mit der aktiven Server-Challenge zur Verifikation", async () => {
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn() },
    });
    render(<OWKSManagement user={user} />);

    fireEvent.click(await screen.findByRole("button", { name: "Kontrollanforderung starten" }));
    fireEvent.click(await screen.findByRole("button", { name: "QR-Code mit Kamera scannen" }));
    await waitFor(() => expect(qrScanner.callback).toBeDefined());
    qrScanner.callback?.({ getText: () => "camera-credential" }, undefined, {
      stop: qrScanner.stop,
    });

    await waitFor(() => expect(api.recordOWKSScan).toHaveBeenCalledWith(
      expect.objectContaining({
        challenge_id: "challenge-1",
        credential: "camera-credential",
        client_event_id: expect.any(String),
      }),
    ));
    expect(await screen.findByText(/Die physische Anwesenheit bleibt unbestätigt/))
      .toBeTruthy();
    expect(qrScanner.stop).toHaveBeenCalled();
  });

  it("speichert Ereignisse offline in der Warteschlange", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    render(<OWKSManagement user={user} />);

    await screen.findByRole("heading", { name: "Online-Wachbuch" });
    fireEvent.change(screen.getByLabelText("Titel"), { target: { value: "Offline-Eintrag" } });
    fireEvent.submit(screen.getByLabelText("Titel").closest("form")!);

    expect(await screen.findByText("Ereignis lokal gespeichert und wartet auf Synchronisierung."))
      .toBeTruthy();
    const queued = JSON.parse(localStorage.getItem("securityops-owks-offline-queue") ?? "[]");
    expect(queued).toHaveLength(1);
    expect(queued[0].title).toBe("Offline-Eintrag");
  });

  it("behält Synchronisierungskonflikte sichtbar und lokal", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    localStorage.setItem("securityops-owks-offline-queue", JSON.stringify([{
      object_id: "object-1",
      event_type: "control",
      title: "Offline-Kontrolle",
      description: "",
      severity: "warning",
      occurred_at: "2026-11-08T19:00:00Z",
      client_event_id: "offline-event-1",
    }]));
    vi.mocked(api.syncOWKSEvents).mockResolvedValue([
      {
        client_event_id: "offline-event-1",
        status: "conflict",
        event: null,
        detail: "Offline-Kontrolle muss geprüft werden.",
      },
    ]);
    render(<OWKSManagement user={user} />);

    await screen.findByRole("heading", { name: "Online-Wachbuch" });
    const syncButton = screen.getByRole("button", { name: "Warteschlange synchronisieren" });
    expect((syncButton as HTMLButtonElement).disabled).toBe(true);
    Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
    window.dispatchEvent(new Event("online"));
    await waitFor(() => expect((syncButton as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Warteschlange synchronisieren" }));

    await waitFor(() => expect(api.syncOWKSEvents).toHaveBeenCalled());
    expect(await screen.findByText("Konflikt – manuelle Prüfung erforderlich")).toBeTruthy();
    expect(api.syncOWKSEvents).toHaveBeenCalledWith(
      expect.arrayContaining([expect.objectContaining({ title: "Offline-Kontrolle" })]),
    );
    await waitFor(() => {
      expect(
        JSON.parse(localStorage.getItem("securityops-owks-offline-queue") ?? "[]"),
      ).toHaveLength(1);
    });
  });

  it("bietet die Vorfallerfassung ausschließlich mit incidents.create an", async () => {
    const event: OWKSEvent = {
      id: "owks-event-1",
      object_id: "object-1",
      route_id: null,
      control_point_id: null,
      corrects_event_id: null,
      employee_id: "employee-1",
      actor_id: "employee-1",
      client_event_id: null,
      event_type: "deviation",
      severity: "critical",
      title: "Originaltitel",
      description: "Sensible Originalbeschreibung",
      occurred_at: "2026-11-09T08:00:00Z",
      sync_status: "synced",
      presence_verified: false,
      status: "open",
      created_at: "2026-11-09T08:00:00Z",
    };
    vi.mocked(api.getOWKSEvents).mockResolvedValue([event]);
    render(<OWKSManagement user={{
      ...user,
      permissions: [...user.permissions, "incidents.create"],
    }} />);

    expect(await screen.findByRole("button", { name: "Als Vorfall erfassen" })).toBeTruthy();

    cleanup();
    const unauthorizedUser = { ...user, permissions: ["owks.read", "owks.write"] };
    render(<OWKSManagement user={unauthorizedUser} />);
    await screen.findByText("Originaltitel");
    expect(screen.queryByRole("button", { name: "Als Vorfall erfassen" })).toBeNull();

    cleanup();
    vi.mocked(api.getIncidentChoices).mockResolvedValue({
      objects: [],
      assignees: [],
      linked_owks_event_ids: [],
    });
    render(<OWKSManagement user={{
      ...user,
      permissions: [...user.permissions, "incidents.create"],
    }} />);
    await screen.findByText("Originaltitel");
    expect(screen.queryByRole("button", { name: "Als Vorfall erfassen" })).toBeNull();
    expect(api.getIncidentChoices).toHaveBeenCalledTimes(2);
  });

  it("sendet die Vorfalldaten mit OWKS-Referenz und ausgewählter Verantwortung", async () => {
    const event: OWKSEvent = {
      id: "owks-event-1",
      object_id: "object-1",
      route_id: null,
      control_point_id: null,
      corrects_event_id: null,
      employee_id: "employee-1",
      actor_id: "employee-1",
      client_event_id: null,
      event_type: "deviation",
      severity: "critical",
      title: "Originaltitel",
      description: "Sensible Originalbeschreibung",
      occurred_at: "2026-11-09T08:00:00Z",
      sync_status: "synced",
      presence_verified: false,
      status: "open",
      created_at: "2026-11-09T08:00:00Z",
    };
    vi.mocked(api.getOWKSEvents).mockResolvedValue([event]);
    render(<OWKSManagement user={{
      ...user,
      permissions: [...user.permissions, "incidents.create"],
    }} />);

    fireEvent.click(await screen.findByRole("button", { name: "Als Vorfall erfassen" }));
    fireEvent.change(screen.getByLabelText("Titel", { selector: "input[name='incident_title']" }), {
      target: { value: "  Beschwerde am Eingang  " },
    });
    fireEvent.change(screen.getByLabelText("Bericht"), {
      target: { value: "  Der Zugang war nicht gesichert.  " },
    });
    fireEvent.change(screen.getByLabelText("Typ"), { target: { value: "complaint" } });
    fireEvent.change(screen.getByLabelText("Schwere"), { target: { value: "high" } });
    fireEvent.change(screen.getByLabelText("Verantwortliche Person"), {
      target: { value: "employee-1" },
    });
    fireEvent.change(screen.getByLabelText("Fällig am (optional)"), {
      target: { value: "2026-11-10T12:30" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Vorfall anlegen" }));

    await waitFor(() => expect(api.createIncident).toHaveBeenCalledWith({
      title: "Beschwerde am Eingang",
      report: "Der Zugang war nicht gesichert.",
      incident_type: "complaint",
      severity: "high",
      object_id: "object-1",
      assigned_to_id: "employee-1",
      due_at: new Date("2026-11-10T12:30").toISOString(),
      owks_event_id: "owks-event-1",
    }));
    expect(api.createIncident).not.toHaveBeenCalledWith(expect.objectContaining({
      report: "Sensible Originalbeschreibung",
    }));
    expect(await screen.findByText("Vorfall wurde angelegt und mit dem OWKS-Ereignis verknüpft."))
      .toBeTruthy();
    expect(await screen.findByText("Bereits mit einem Vorgang verknüpft")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Als Vorfall erfassen" })).toBeNull();
  });

  it("markiert bereits verknüpfte Ereignisse ohne Vorfalldetails", async () => {
    vi.mocked(api.getOWKSEvents).mockResolvedValue([{
      id: "owks-event-1",
      object_id: "object-1",
      route_id: null,
      control_point_id: null,
      corrects_event_id: null,
      employee_id: null,
      actor_id: null,
      client_event_id: null,
      event_type: "entry",
      severity: "warning",
      title: "Ereignis",
      description: "",
      occurred_at: "2026-11-09T08:00:00Z",
      sync_status: "synced",
      presence_verified: false,
      status: "open",
      created_at: "2026-11-09T08:00:00Z",
    }]);
    vi.mocked(api.getIncidentChoices).mockResolvedValue({
      objects: [{ id: "object-1", code: "OBJ-1", name: "Testobjekt" }],
      assignees: [{ id: "employee-1", full_name: "Testwache" }],
      linked_owks_event_ids: ["owks-event-1"],
    });
    render(<OWKSManagement user={{
      ...user,
      permissions: [...user.permissions, "incidents.create"],
    }} />);

    expect(await screen.findByText("Bereits mit einem Vorgang verknüpft")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Als Vorfall erfassen" })).toBeNull();
    expect(screen.queryByText("Vorfalldetails")).toBeNull();
  });

  it("markiert ein paralleles Duplikat nach HTTP 409 als verknüpft", async () => {
    vi.mocked(api.getOWKSEvents).mockResolvedValue([{
      id: "owks-event-1",
      object_id: "object-1",
      route_id: null,
      control_point_id: null,
      corrects_event_id: null,
      employee_id: null,
      actor_id: null,
      client_event_id: null,
      event_type: "entry",
      severity: "warning",
      title: "Ereignis",
      description: "",
      occurred_at: "2026-11-09T08:00:00Z",
      sync_status: "synced",
      presence_verified: false,
      status: "open",
      created_at: "2026-11-09T08:00:00Z",
    }]);
    vi.mocked(api.createIncident).mockRejectedValue(
      new Error("Dieses OWKS-Ereignis ist bereits mit einem Vorgang verknüpft."),
    );
    render(<OWKSManagement user={{
      ...user,
      permissions: [...user.permissions, "incidents.create"],
    }} />);

    fireEvent.click(await screen.findByRole("button", { name: "Als Vorfall erfassen" }));
    fireEvent.change(screen.getByLabelText("Titel", { selector: "input[name='incident_title']" }), {
      target: { value: "Vorfall" },
    });
    fireEvent.change(screen.getByLabelText("Bericht"), { target: { value: "Bericht" } });
    fireEvent.change(screen.getByLabelText("Verantwortliche Person"), {
      target: { value: "employee-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Vorfall anlegen" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Dieses OWKS-Ereignis ist bereits mit einem Vorgang verknüpft.",
    );
    expect(await screen.findByText("Bereits mit einem Vorgang verknüpft")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Als Vorfall erfassen" })).toBeNull();
  });

  it.each([
    [403, "Keine Berechtigung, diesen Vorfall zu erfassen oder das Objekt zu bearbeiten."],
    [404, "Das OWKS-Ereignis oder Objekt ist nicht vorhanden oder nicht zugänglich."],
    [422, "Die Angaben sind ungültig. Bitte Titel, Bericht, Verantwortliche und OWKS-Bezug prüfen."],
  ])("zeigt Fehler %s bei Vorfallerfassung verständlich auf Deutsch", async (status, expected) => {
    vi.mocked(api.getOWKSEvents).mockResolvedValue([{
      id: "owks-event-1",
      object_id: "object-1",
      route_id: null,
      control_point_id: null,
      corrects_event_id: null,
      employee_id: null,
      actor_id: null,
      client_event_id: null,
      event_type: "entry",
      severity: "warning",
      title: "Ereignis",
      description: "",
      occurred_at: "2026-11-09T08:00:00Z",
      sync_status: "synced",
      presence_verified: false,
      status: "open",
      created_at: "2026-11-09T08:00:00Z",
    }]);
    vi.mocked(api.createIncident).mockRejectedValue(new Error(`Serverfehler (${status})`));
    render(<OWKSManagement user={{
      ...user,
      permissions: [...user.permissions, "incidents.create"],
    }} />);

    fireEvent.click(await screen.findByRole("button", { name: "Als Vorfall erfassen" }));
    fireEvent.change(screen.getByLabelText("Titel", { selector: "input[name='incident_title']" }), {
      target: { value: "Vorfall" },
    });
    fireEvent.change(screen.getByLabelText("Bericht"), { target: { value: "Bericht" } });
    fireEvent.change(screen.getByLabelText("Verantwortliche Person"), {
      target: { value: "employee-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Vorfall anlegen" }));

    expect((await screen.findByRole("alert")).textContent).toContain(expected);
  });

  it("validiert Titel und Bericht vor dem POST", async () => {
    vi.mocked(api.getOWKSEvents).mockResolvedValue([{
      id: "owks-event-1",
      object_id: "object-1",
      route_id: null,
      control_point_id: null,
      corrects_event_id: null,
      employee_id: null,
      actor_id: null,
      client_event_id: null,
      event_type: "entry",
      severity: "warning",
      title: "Ereignis",
      description: "",
      occurred_at: "2026-11-09T08:00:00Z",
      sync_status: "synced",
      presence_verified: false,
      status: "open",
      created_at: "2026-11-09T08:00:00Z",
    }]);
    render(<OWKSManagement user={{
      ...user,
      permissions: [...user.permissions, "incidents.create"],
    }} />);

    fireEvent.click(await screen.findByRole("button", { name: "Als Vorfall erfassen" }));
    fireEvent.change(screen.getByLabelText("Titel", { selector: "input[name='incident_title']" }), {
      target: { value: "   " },
    });
    fireEvent.change(screen.getByLabelText("Bericht"), { target: { value: "   " } });
    fireEvent.submit(screen.getByLabelText("Bericht").closest("form")!);

    expect((await screen.findByRole("alert")).textContent)
      .toContain("Bitte Titel und Bericht ausfüllen");
    expect(api.createIncident).not.toHaveBeenCalled();
  });

  it("erstellt eine Schichtübergabe mit strukturiertem und automatisch übernommenem Punkt", async () => {
    vi.mocked(api.getOWKSShiftHandoverContext).mockResolvedValue({
      current_employee_id: "employee-1",
      shifts: [{
        id: "shift-1",
        starts_at: "2026-11-09T06:00:00Z",
        ends_at: "2026-11-09T14:00:00Z",
      }],
      recipients: [{ id: "employee-2", full_name: "Nachfolger" }],
      source_items: [{
        source_type: "owks_event",
        source_id: "event-source-1",
        title: "Offene Zugangsstörung",
        status: "open",
        severity: "warning",
        occurred_at: "2026-11-09T12:00:00Z",
      }, {
        source_type: "instruction",
        source_id: "instruction-source-1",
        title: "Zutrittskontrolle",
        status: "overdue",
        severity: "warning",
        occurred_at: "2026-11-09T10:00:00Z",
      }],
    });
    vi.mocked(api.createOWKSShiftHandover).mockResolvedValue({
      id: "handover-1",
      object_id: "object-1",
      event_id: "event-1",
      shift_id: "shift-1",
      shift_starts_at: "2026-11-09T06:00:00Z",
      shift_ends_at: "2026-11-09T14:00:00Z",
      sender_employee_id: "employee-1",
      sender_name: "Testwache",
      recipient_employee_id: "employee-2",
      recipient_name: "Nachfolger",
      handover_text: "Zugang prüfen",
      structured_items: [{ category: "disturbance", text: "Türschließer prüfen" }],
      source_items: [],
      status: "pending",
      created_at: "2026-11-09T14:00:00Z",
      confirmed_at: null,
      confirmation_note: null,
      history: [{
        action: "submitted",
        employee_id: "employee-1",
        actor_id: "user-1",
        note: "",
        occurred_at: "2026-11-09T14:00:00Z",
      }],
    });
    render(<OWKSManagement user={user} />);

    expect(await screen.findByText(/Offene Zugangsstörung/)).toBeTruthy();
    expect(await screen.findByText(
      /Anweisung: Zutrittskontrolle · Überfällig · Warnung/,
    )).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Eigene veröffentlichte Schicht"), {
      target: { value: "shift-1" },
    });
    fireEvent.change(screen.getByLabelText("Übernehmende Person"), {
      target: { value: "employee-2" },
    });
    fireEvent.change(screen.getByLabelText("Übergabetext"), {
      target: { value: "Zugang prüfen" },
    });
    fireEvent.change(screen.getByLabelText("Text Übergabepunkt 1"), {
      target: { value: "Türschließer prüfen" },
    });
    fireEvent.change(screen.getByLabelText("Kategorie Übergabepunkt 1"), {
      target: { value: "disturbance" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Übergabe speichern" }));

    await waitFor(() => expect(api.createOWKSShiftHandover).toHaveBeenCalledWith(
      "object-1",
      {
        shift_id: "shift-1",
        recipient_employee_id: "employee-2",
        handover_text: "Zugang prüfen",
        structured_items: [{ category: "disturbance", text: "Türschließer prüfen" }],
      },
    ));
    expect(await screen.findByText(/wurde unveränderlich gespeichert/)).toBeTruthy();
  });
});
