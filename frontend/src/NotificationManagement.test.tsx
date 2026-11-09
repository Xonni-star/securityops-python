// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NotificationManagement from "./NotificationManagement";
import * as api from "./api";

vi.mock("./api", () => ({
  getNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
}));

const notification = {
  id: "notification-1",
  task_id: "task-1",
  object_id: null,
  invoice_id: null,
  event_type: "task.assigned" as const,
  title: "Neue Aufgabe zugewiesen",
  body: "Kontrollbericht prüfen",
  created_at: "2026-11-01T10:00:00Z",
  read_at: null,
};

describe("Benachrichtigungen", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getNotifications).mockResolvedValue({
      items: [notification],
      total: 1,
      unread_count: 1,
      limit: 25,
      offset: 0,
    });
    vi.mocked(api.markNotificationRead).mockResolvedValue({
      ...notification,
      read_at: "2026-11-01T10:05:00Z",
    });
  });

  it("zeigt ungelesene Ereignisse und aktualisiert ihren Lesestatus", async () => {
    vi.mocked(api.getNotifications)
      .mockResolvedValueOnce({
        items: [notification],
        total: 1,
        unread_count: 1,
        limit: 25,
        offset: 0,
      })
      .mockResolvedValueOnce({
        items: [{ ...notification, read_at: "2026-11-01T10:05:00Z" }],
        total: 1,
        unread_count: 0,
        limit: 25,
        offset: 0,
      });
    render(<NotificationManagement />);

    expect(await screen.findByText("Kontrollbericht prüfen")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Als gelesen markieren" }));
    await waitFor(() => {
      expect(api.markNotificationRead).toHaveBeenCalledWith("notification-1");
    });
    expect(await screen.findByText("Gelesen")).toBeTruthy();
  });

  it("zeigt einen leeren Zustand ohne Benachrichtigungen", async () => {
    vi.mocked(api.getNotifications).mockResolvedValueOnce({
      items: [],
      total: 0,
      unread_count: 0,
      limit: 25,
      offset: 0,
    });
    render(<NotificationManagement />);
    expect(await screen.findByText("Keine Benachrichtigungen vorhanden.")).toBeTruthy();
  });
});
