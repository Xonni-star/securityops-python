import { afterEach, describe, expect, it, vi } from "vitest";

import { exportBillingInvoiceCsv } from "./api";

describe("CSV-Rechnungsexport-API", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = "securityops_csrf=; path=/; max-age=0";
  });

  it("sendet einen authentifizierten CSRF-geschützten POST und liefert den Dateiblob", async () => {
    document.cookie = "securityops_csrf=csrf%2Btoken; path=/";
    const blob = new Blob(["csv"], { type: "text/csv" });
    const response = {
      ok: true,
      status: 200,
      blob: vi.fn().mockResolvedValue(blob),
    } as unknown as Response;
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);

    const result = await exportBillingInvoiceCsv("invoice-1", "csv-key-0001");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/billing/invoices/invoice-1/exports/csv?idempotency_key=csv-key-0001",
      {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRF-Token": "csrf+token" },
      },
    );
    expect(response.blob).toHaveBeenCalledOnce();
    expect(result).toBe(blob);
  });
});
