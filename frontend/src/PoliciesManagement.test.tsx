import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PoliciesManagement from "./PoliciesManagement";
import {
  confirmPolicy,
  getMyPolicyAssignments,
  recordPolicyRead,
} from "./api";

vi.mock("./api", () => ({
  assignPolicy: vi.fn(),
  confirmPolicy: vi.fn(),
  createPolicy: vi.fn(),
  createPolicyVersion: vi.fn(),
  exportPolicyProof: vi.fn(),
  getMyPolicyAssignments: vi.fn(),
  getPolicies: vi.fn(),
  getPolicyEmployees: vi.fn(),
  getPolicyHistory: vi.fn(),
  getPolicyObjects: vi.fn(),
  recordPolicyRead: vi.fn(),
}));

const assignment = {
  id: "assignment-1",
  policy_id: "policy-1",
  kind: "training" as const,
  title: "Arbeitsschutz",
  object_id: null,
  object_name: null,
  version_id: "version-1",
  version_number: 1,
  content: "Testinhalt der Unterweisung",
  valid_from: "2026-01-01T00:00:00Z",
  valid_until: null,
  cycle_number: 1,
  due_at: null,
  read_at: null,
  confirmed_at: null,
  overdue: false,
  reminder_due: false,
};

describe("PoliciesManagement", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getMyPolicyAssignments).mockResolvedValue([assignment]);
    vi.mocked(recordPolicyRead).mockResolvedValue({ ...assignment, read_at: "2026-11-09T12:00:00Z" });
    vi.mocked(confirmPolicy).mockResolvedValue({
      ...assignment,
      read_at: "2026-11-09T12:00:00Z",
      confirmed_at: "2026-11-09T12:01:00Z",
    });
  });

  it("requires a saved read receipt before the employee can confirm", async () => {
    const { rerender } = render(<PoliciesManagement canManage={false} canReadOwn />);
    expect(await screen.findByText("Testinhalt der Unterweisung")).toBeTruthy();
    const confirmButton = screen.getByRole("button", { name: "Bestätigung abgeben" });
    expect((confirmButton as HTMLButtonElement).disabled).toBe(true);

    vi.mocked(getMyPolicyAssignments).mockResolvedValue([
      { ...assignment, read_at: "2026-11-09T12:00:00Z" },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Als gelesen markieren" }));
    await waitFor(() => expect(recordPolicyRead).toHaveBeenCalledWith("assignment-1"));

    rerender(<PoliciesManagement canManage={false} canReadOwn />);
    await waitFor(() => {
      expect((screen.getByRole("button", { name: "Bestätigung abgeben" }) as HTMLButtonElement).disabled)
        .toBe(false);
    });
    fireEvent.click(screen.getByRole("button", { name: "Bestätigung abgeben" }));
    await waitFor(() => expect(confirmPolicy).toHaveBeenCalledWith("assignment-1"));
  });
});
