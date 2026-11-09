// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import InventoryManagement from "./InventoryManagement";
import * as api from "./api";

vi.mock("./api", () => ({
  archiveInventoryAsset: vi.fn(),
  createInventoryAsset: vi.fn(),
  createInventoryEvent: vi.fn(),
  getInventoryAssets: vi.fn(),
  getInventoryEligibleEmployees: vi.fn(),
  getInventoryEvents: vi.fn(),
  getInventoryEmployees: vi.fn(),
  getInventoryObjects: vi.fn(),
  updateInventoryAsset: vi.fn(),
}));

const asset = {
  id: "asset-1",
  asset_number: "I-001",
  serial_number: "SER-001",
  name: "Funkgerät",
  category: "radio" as const,
  condition: "good" as const,
  status: "available" as const,
  location: "Materialraum",
  object_id: "object-1",
  object_code: "OBJ-001",
  object_name: "Verwaltungsgebäude",
  current_employee_id: null,
  current_employee_name: null,
  archived_at: null,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

const employee = {
  id: "employee-1",
  employee_number: "MA-001",
  full_name: "Erika Beispiel",
};

describe("Inventarverwaltung", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getInventoryAssets).mockResolvedValue({
      items: [asset],
      total: 1,
      limit: 25,
      offset: 0,
    });
    vi.mocked(api.getInventoryObjects).mockResolvedValue([
      { id: "object-1", code: "OBJ-001", name: "Verwaltungsgebäude" },
    ]);
    vi.mocked(api.getInventoryEmployees).mockResolvedValue([]);
    vi.mocked(api.getInventoryEligibleEmployees).mockResolvedValue([employee]);
    vi.mocked(api.getInventoryEvents).mockResolvedValue({
      items: [{
        id: "event-1",
        asset_id: asset.id,
        asset_number: asset.asset_number,
        object_id: asset.object_id,
        object_name: asset.object_name,
        from_object_id: null,
        from_object_name: null,
        to_object_id: asset.object_id,
        to_object_name: asset.object_name,
        from_employee_id: null,
        from_employee_name: null,
        to_employee_id: null,
        to_employee_name: null,
        actor_id: "actor-1",
        actor_name: "Test Administration",
        event_type: "created",
        status_after: "available",
        condition_after: "good",
        location_after: "Materialraum",
        acknowledged_at: null,
        acknowledgement_note: null,
        note: null,
        created_at: "2026-11-02T10:00:00Z",
      }],
      total: 1,
      limit: 100,
      offset: 0,
    });
    vi.mocked(api.createInventoryEvent).mockResolvedValue({
      id: "event-2",
      asset_id: asset.id,
      asset_number: asset.asset_number,
      object_id: asset.object_id,
      object_name: asset.object_name,
      from_object_id: null,
      from_object_name: null,
      to_object_id: asset.object_id,
      to_object_name: asset.object_name,
      from_employee_id: null,
      from_employee_name: null,
      to_employee_id: employee.id,
      to_employee_name: employee.full_name,
      actor_id: "actor-1",
      actor_name: "Test Administration",
      event_type: "issued",
      status_after: "issued",
      condition_after: "good",
      location_after: "Materialraum",
      acknowledged_at: "2026-11-02T10:00:00Z",
      acknowledgement_note: null,
      note: null,
      created_at: "2026-11-02T10:00:00Z",
    });
  });

  it("zeigt Inventardaten und die protokollierte Historie", async () => {
    render(<InventoryManagement canManage={false} canManageGlobal={false} canMove={false} />);
    expect(await screen.findByText("I-001")).toBeTruthy();
    expect(screen.getByText("Funkgerät · Funkgeräte")).toBeTruthy();
    expect(screen.getByText("OBJ-001 · Verwaltungsgebäude", { selector: "p" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Historie" }));
    expect(await screen.findByText("Erfasst")).toBeTruthy();
    expect(screen.getByText(/Test Administration/)).toBeTruthy();
  });

  it("filtert und hebt den über die globale Suche geöffneten Treffer hervor", async () => {
    const { container } = render(
      <InventoryManagement
        canManage={false}
        canManageGlobal={false}
        canMove={false}
        initialAssetId={asset.id}
        initialQuery={asset.asset_number}
      />,
    );

    await screen.findByText("I-001");
    await waitFor(() => {
      expect(api.getInventoryAssets).toHaveBeenCalledWith(
        expect.objectContaining({ q: asset.asset_number }),
      );
    });
    expect(container.querySelector(".key-card.search-result-row")).toBeTruthy();
  });

  it("erfordert eine Quittierung für die Ausgabe und sendet sie an die API", async () => {
    render(<InventoryManagement canManage={false} canManageGlobal={false} canMove />);
    fireEvent.click(await screen.findByRole("button", { name: "Ausgeben" }));
    await screen.findByRole("option", { name: "MA-001 · Erika Beispiel" });
    fireEvent.change(screen.getAllByLabelText("Mitarbeiter").at(-1)!, {
      target: { value: employee.id },
    });
    const acknowledgement = screen.getByRole("checkbox", {
      name: "Empfang durch den ausgewählten Mitarbeiter bestätigt",
    });
    fireEvent.change(acknowledgement, { target: { checked: true } });
    expect((acknowledgement as HTMLInputElement).checked).toBe(true);
    fireEvent.submit(screen.getByRole("button", { name: "Vorgang protokollieren" }).closest("form")!);
    await waitFor(() => {
      expect(api.createInventoryEvent).toHaveBeenCalledWith(asset.id, {
        event_type: "issued",
        employee_id: employee.id,
        acknowledged: true,
        acknowledgement_note: undefined,
        location: asset.location,
        note: undefined,
      });
    });
  });

  it("legt mit Verwaltungsrecht einen Inventargegenstand an", async () => {
    vi.mocked(api.createInventoryAsset).mockResolvedValue(asset);
    render(<InventoryManagement canManage canManageGlobal canMove={false} />);
    fireEvent.click(await screen.findByRole("button", { name: "Inventar erfassen" }));
    fireEvent.change(screen.getByLabelText("Inventarnummer"), { target: { value: "I-NEW" } });
    fireEvent.change(screen.getByLabelText("Seriennummer"), { target: { value: "S-NEW" } });
    fireEvent.change(screen.getByLabelText("Bezeichnung"), { target: { value: "Tablet" } });
    fireEvent.change(screen.getByLabelText("Standort"), { target: { value: "Lager" } });
    fireEvent.click(screen.getByRole("button", { name: "Inventargegenstand speichern" }));
    await waitFor(() => {
      expect(api.createInventoryAsset).toHaveBeenCalledWith({
        asset_number: "I-NEW",
        serial_number: "S-NEW",
        name: "Tablet",
        category: "other",
        condition: "good",
        location: "Lager",
        object_id: undefined,
      });
    });
  });

  it("zeigt leere und Fehlerzustände", async () => {
    vi.mocked(api.getInventoryAssets).mockResolvedValueOnce({
      items: [],
      total: 0,
      limit: 25,
      offset: 0,
    });
    const empty = render(<InventoryManagement canManage={false} canManageGlobal={false} canMove={false} />);
    expect(await screen.findByText("Keine Inventargegenstände für diese Auswahl vorhanden.")).toBeTruthy();
    empty.unmount();

    vi.mocked(api.getInventoryAssets).mockRejectedValueOnce(new Error("Register nicht erreichbar"));
    render(<InventoryManagement canManage={false} canManageGlobal={false} canMove={false} />);
    expect((await screen.findByRole("alert")).textContent).toContain("Register nicht erreichbar");
  });
});
