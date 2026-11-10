import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BillingManagement from "./BillingManagement";
import type { AuthUser, BillingInvoice, Customer } from "./types";

const api = vi.hoisted(() => ({
  getBillingRates: vi.fn(),
  getBillingInvoices: vi.fn(),
  getCustomers: vi.fn(),
  exportBillingInvoiceCsv: vi.fn(),
}));

vi.mock("./api", () => api);

const user: AuthUser = {
  id: "billing-user",
  username: "buchhaltung",
  email: "billing@example.com",
  full_name: "Test Buchhaltung",
  is_active: true,
  roles: ["accounting"],
  permissions: [
    "billing.invoices.read",
    "billing.invoices.approve",
    "billing.exports.create",
    "customers.read",
  ],
};

const customer: Customer = {
  id: "customer-1",
  customer_number: "K-TEST-1",
  company_name: "Testkunde Rechnungswesen",
  status: "active",
  contract_status: "active",
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
  created_at: "2026-11-08T10:00:00Z",
  updated_at: "2026-11-08T10:00:00Z",
};

const invoice: BillingInvoice = {
  id: "invoice-1",
  invoice_number: "R-2026-TEST-0001",
  customer_id: customer.id,
  contract_id: null,
  kind: "invoice",
  status: "draft",
  payment_status: "open",
  dunning_status: "none",
  currency: "EUR",
  issued_on: "2026-11-08",
  due_on: "2026-12-08",
  correction_of_id: null,
  correction_reason: null,
  net_amount: "100.00",
  tax_amount: "19.00",
  gross_amount: "119.00",
  approved_at: null,
  archived_at: null,
  created_at: "2026-11-08T10:00:00Z",
  lines: [],
};

describe("Rechnungswesen", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    api.getBillingRates.mockResolvedValue([]);
    api.getBillingInvoices.mockResolvedValue([invoice]);
    api.getCustomers.mockResolvedValue({ items: [customer], total: 1 });
    api.exportBillingInvoiceCsv.mockResolvedValue(new Blob(["csv"], { type: "text/csv" }));
  });

  it("zeigt Rechnungsentwürfe und Freigabe nur mit passender Berechtigung", async () => {
    render(<BillingManagement user={user} />);

    expect(await screen.findByText("R-2026-TEST-0001")).toBeTruthy();
    expect(screen.getByText("Testkunde Rechnungswesen")).toBeTruthy();
    expect(screen.getByText("Entwurf")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Freigeben" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "PDF" })).toBeNull();
    expect(screen.queryByRole("button", { name: "CSV herunterladen" })).toBeNull();
    expect(api.getBillingInvoices).toHaveBeenCalledOnce();
  });

  it("lädt den CSV-Export für archivierte Rechnungen als Datei herunter", async () => {
    api.getBillingInvoices.mockResolvedValue([{ ...invoice, status: "archived" }]);
    const clickedAnchors: HTMLAnchorElement[] = [];
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:rechnung"),
      revokeObjectURL: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clickedAnchors.push(this);
    });
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000001");

    render(<BillingManagement user={user} />);

    fireEvent.click(await screen.findByRole("button", { name: "CSV herunterladen" }));
    await waitFor(() => {
      expect(api.exportBillingInvoiceCsv).toHaveBeenCalledWith(
        invoice.id,
        "00000000-0000-4000-8000-000000000001",
      );
    });
    expect(clickedAnchors).toHaveLength(1);
    expect(clickedAnchors[0].download).toBe(`${invoice.invoice_number}.csv`);
    expect(clickedAnchors[0].href).toBe("blob:rechnung");
    expect((await screen.findByRole("status")).textContent).toContain(
      "CSV-Rechnungsexport heruntergeladen.",
    );
  });

  it("zeigt CSV-Downloads ohne Exportberechtigung nicht an", async () => {
    api.getBillingInvoices.mockResolvedValue([{ ...invoice, status: "approved" }]);
    const userWithoutExport = {
      ...user,
      permissions: user.permissions.filter((permission) => permission !== "billing.exports.create"),
    };

    render(<BillingManagement user={userWithoutExport} />);

    expect(await screen.findByText("R-2026-TEST-0001")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "CSV herunterladen" })).toBeNull();
  });
});
