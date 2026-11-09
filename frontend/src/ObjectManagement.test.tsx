// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ObjectManagement from "./ObjectManagement";
import * as api from "./api";
import type { AuthUser, SecurityObject } from "./types";

vi.mock("./api", () => ({
  archiveObject: vi.fn(),
  createObject: vi.fn(),
  createObjectContact: vi.fn(),
  deleteObjectContact: vi.fn(),
  getCustomers: vi.fn(),
  getObject: vi.fn(),
  getObjectAssignmentCandidates: vi.fn(),
  getObjectAssignments: vi.fn(),
  getObjectHistory: vi.fn(),
  getObjects: vi.fn(),
  getObjectSecurity: vi.fn(),
  reactivateObject: vi.fn(),
  updateObject: vi.fn(),
  updateObjectAssignments: vi.fn(),
  updateObjectContact: vi.fn(),
  updateObjectSecurity: vi.fn(),
}));

const user: AuthUser = {
  id: "user-1",
  username: "verwaltung",
  email: "verwaltung@example.test",
  full_name: "Objektverwaltung",
  is_active: true,
  roles: ["administrator"],
  permissions: ["objects.read", "objects.manage", "objects.manage_all", "customers.read"],
};

const object: SecurityObject = {
  id: "object-1",
  customer_id: "customer-1",
  customer_name: "Testkunde",
  code: "OBJ-001",
  name: "Testobjekt",
  object_type: null,
  description: null,
  status: "active",
  operating_hours: null,
  service_times: null,
  staffing_requirements: null,
  archived_at: null,
  address: null,
  contacts: [],
  qualification_requirements: ["Erste Hilfe"],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Objektqualifikationsanforderungen", () => {
  it("sendet die zeilenweise gepflegten Anforderungen als Liste", async () => {
    vi.mocked(api.getObjects).mockResolvedValue({
      items: [object],
      total: 1,
      limit: 25,
      offset: 0,
    });
    vi.mocked(api.getCustomers).mockResolvedValue({
      items: [],
      total: 0,
      limit: 100,
      offset: 0,
    });
    vi.mocked(api.getObject).mockResolvedValue(object);
    vi.mocked(api.getObjectHistory).mockResolvedValue([]);
    vi.mocked(api.updateObject).mockImplementation(async (_id, data) => ({
      ...object,
      qualification_requirements: data.qualification_requirements ?? [],
    }));

    render(
      <ObjectManagement
        user={user}
        initialObjectId={object.id}
        onInitialObjectOpened={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getAllByLabelText("Für Dienste erforderliche Qualifikationen (je Zeile eine)"),
      ).toHaveLength(2);
    });
    const requirementFields = screen.getAllByLabelText(
      "Für Dienste erforderliche Qualifikationen (je Zeile eine)",
    );
    fireEvent.change(requirementFields[1], {
      target: { value: "  Erste Hilfe  \nWaffensachkunde\n\n" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Änderungen speichern" }));

    await waitFor(() => {
      expect(api.updateObject).toHaveBeenCalledWith(
        object.id,
        expect.objectContaining({
          qualification_requirements: ["Erste Hilfe", "Waffensachkunde"],
        }),
      );
    });
  });
});
