// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import GlobalSearch from "./GlobalSearch";
import * as api from "./api";

vi.mock("./api", () => ({
  getGlobalSearch: vi.fn(),
}));

describe("globale Suche", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sucht nur verfügbare Entitäten und öffnet einen konkreten Treffer", async () => {
    const result = {
      id: "customer-1",
      type: "customer" as const,
      title: "Beispiel GmbH",
      reference: "K-123",
    };
    vi.mocked(api.getGlobalSearch).mockResolvedValue({
      items: [result],
      total: 1,
      limit: 10,
      offset: 0,
    });
    const onOpenResult = vi.fn();
    render(<GlobalSearch availableTypes={["customer"]} onOpenResult={onOpenResult} />);

    fireEvent.change(screen.getByLabelText("Freigegebene Bereiche durchsuchen"), {
      target: { value: "Beispiel" },
    });

    fireEvent.click(await screen.findByRole("button", { name: "Öffnen" }));
    expect(api.getGlobalSearch).toHaveBeenCalledWith({
      q: "Beispiel",
      type: "",
      limit: 10,
      offset: 0,
    });
    expect(screen.queryByRole("combobox", { name: "Suchbereich" })).toBeNull();
    expect(onOpenResult).toHaveBeenCalledWith(result);
  });

  it("zeigt Fehler der Suche sichtbar an", async () => {
    vi.mocked(api.getGlobalSearch).mockRejectedValue(new Error("Suche nicht verfügbar"));
    render(<GlobalSearch availableTypes={["customer", "object"]} onOpenResult={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Freigegebene Bereiche durchsuchen"), {
      target: { value: "Objekt" },
    });

    expect((await screen.findByRole("alert")).textContent).toContain("Suche nicht verfügbar");
    expect(screen.getByRole("combobox", { name: "Suchbereich" })).toBeTruthy();
  });

  it("paginiert Treffer serverseitig", async () => {
    vi.mocked(api.getGlobalSearch).mockResolvedValue({
      items: Array.from({ length: 10 }, (_, index) => ({
        id: `customer-${index}`,
        type: "customer" as const,
        title: `Kunde ${index}`,
        reference: `K-${index}`,
      })),
      total: 11,
      limit: 10,
      offset: 0,
    });
    render(<GlobalSearch availableTypes={["customer"]} onOpenResult={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Freigegebene Bereiche durchsuchen"), {
      target: { value: "Kunde" },
    });

    fireEvent.click(await screen.findByRole("button", { name: "Weiter" }));

    await waitFor(() => {
      expect(api.getGlobalSearch).toHaveBeenLastCalledWith({
        q: "Kunde",
        type: "",
        limit: 10,
        offset: 10,
      });
    });
  });

  it("zeigt nur bereitgestellte Suchtypen mit deutschen Bezeichnungen", () => {
    render(<GlobalSearch
      availableTypes={["customer", "employee", "document", "contract", "task"]}
      onOpenResult={vi.fn()}
    />);

    const options = Array.from(
      screen.getByRole("combobox", { name: "Suchbereich" }).querySelectorAll("option"),
    ).map((option) => option.textContent);
    expect(options).toEqual(["Alle Treffer", "Kunde", "Mitarbeiter", "Dokument", "Vertrag", "Aufgabe"]);
  });
});
