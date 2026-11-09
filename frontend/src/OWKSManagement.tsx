import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  createOWKSChallenge,
  createOWKSControlPoint,
  createOWKSEvent,
  createOWKSShiftHandover,
  createOWKSRoute,
  createIncident,
  confirmOWKSShiftHandover,
  getOWKSControlPoints,
  getOWKSAttachments,
  getOWKSEvent,
  getOWKSEvents,
  getOWKSShiftHandoverContext,
  getOWKSShiftHandovers,
  getOWKSObjects,
  getOWKSRoutes,
  getIncidentChoices,
  monitorOWKSRoute,
  owksAttachmentUrl,
  recordOWKSScan,
  syncOWKSEvents,
  updateOWKSEventStatus,
  uploadOWKSAttachment,
} from "./api";
import {
  OWKSControlPointQr,
  OWKSScanTools,
  supportsWebNfc,
} from "./OWKSScanTools";
import type {
  AuthUser,
  OWKSControlPoint,
  OWKSAttachment,
  OWKSEvent,
  OWKSObject,
  OWKSRoute,
  OWKSSyncResult,
  OWKSHandoverSource,
  OWKSShiftHandover,
  OWKSShiftHandoverContext,
  OWKSStructuredHandoverItem,
  OWKSHandoverCategory,
  IncidentChoices,
  IncidentSeverity,
  IncidentType,
} from "./types";

type OfflineItem = {
  object_id: string;
  event_type: "entry" | "handover" | "deviation" | "notification" | "manipulation" | "control";
  title: string;
  description: string;
  severity: "info" | "warning" | "critical";
  occurred_at: string;
  client_event_id: string;
};
type NewOfflineItem = Omit<OfflineItem, "event_type"> & {
  event_type: Exclude<OfflineItem["event_type"], "control">;
};

const QUEUE_KEY = "securityops-owks-offline-queue";
const HANDOVER_CATEGORIES: Array<{ value: OWKSHandoverCategory; label: string }> = [
  { value: "task", label: "Aufgabe" },
  { value: "incident", label: "Vorfall" },
  { value: "key", label: "Schlüssel" },
  { value: "disturbance", label: "Störung" },
  { value: "control", label: "Kontrolle" },
  { value: "instruction", label: "Anweisung" },
  { value: "measure", label: "Maßnahme" },
  { value: "other", label: "Sonstiges" },
];

function messageFrom(reason: unknown) {
  return reason instanceof Error ? reason.message : "Die OWKS-Aktion ist fehlgeschlagen.";
}

function incidentMessageFrom(reason: unknown) {
  const message = messageFrom(reason);
  if (message === "Serverfehler (403)") {
    return "Keine Berechtigung, diesen Vorfall zu erfassen oder das Objekt zu bearbeiten.";
  }
  if (message === "Serverfehler (404)") {
    return "Das OWKS-Ereignis oder Objekt ist nicht vorhanden oder nicht zugänglich.";
  }
  if (message === "Serverfehler (422)") {
    return "Die Angaben sind ungültig. Bitte Titel, Bericht, Verantwortliche und OWKS-Bezug prüfen.";
  }
  return message;
}

function handoverSourceSummary(source: OWKSHandoverSource) {
  const sourceLabels: Record<OWKSHandoverSource["source_type"], string> = {
    owks_event: "Wachbuch",
    task: "Aufgabe",
    incident: "Vorfall",
    incident_measure: "Maßnahme",
    key: "Schlüssel",
    inventory_asset: "Inventar",
    instruction: "Anweisung",
  };
  const statusLabels: Record<string, string> = {
    open: "Offen",
    in_progress: "In Bearbeitung",
    blocked: "Blockiert",
    reported: "Gemeldet",
    investigating: "In Prüfung",
    action_required: "Maßnahme erforderlich",
    issued: "Ausgegeben",
    lost: "Vermisst",
    defective: "Defekt",
    maintenance: "Wartung",
    damaged: "Beschädigt",
    pending: "Ausstehend",
    overdue: "Überfällig",
  };
  const severityLabels: Record<string, string> = {
    info: "Hinweis",
    warning: "Warnung",
    critical: "Kritisch",
    low: "Niedrig",
    medium: "Mittel",
    high: "Hoch",
  };
  const status = statusLabels[source.status] ?? source.status;
  const severity = source.severity ? severityLabels[source.severity] ?? source.severity : null;
  return `${sourceLabels[source.source_type]}: ${source.title} · ${status}${severity ? ` · ${severity}` : ""}`;
}

export default function OWKSManagement({
  user,
  initialEventId = null,
}: {
  user: AuthUser;
  initialEventId?: string | null;
}) {
  const [objects, setObjects] = useState<OWKSObject[]>([]);
  const [selectedObjectId, setSelectedObjectId] = useState("");
  const [events, setEvents] = useState<OWKSEvent[]>([]);
  const [handovers, setHandovers] = useState<OWKSShiftHandover[]>([]);
  const [handoverContext, setHandoverContext] = useState<OWKSShiftHandoverContext | null>(null);
  const [handoverItems, setHandoverItems] = useState<OWKSStructuredHandoverItem[]>([
    { category: "other", text: "" },
  ]);
  const [confirmationNotes, setConfirmationNotes] = useState<Record<string, string>>({});
  const [incidentChoices, setIncidentChoices] = useState<IncidentChoices | null>(null);
  const [incidentEvent, setIncidentEvent] = useState<OWKSEvent | null>(null);
  const [focusedEvent, setFocusedEvent] = useState<OWKSEvent | null>(null);
  const [attachments, setAttachments] = useState<Record<string, OWKSAttachment[]>>({});
  const [attachmentsOpen, setAttachmentsOpen] = useState<string[]>([]);
  const [points, setPoints] = useState<OWKSControlPoint[]>([]);
  const [routes, setRoutes] = useState<OWKSRoute[]>([]);
  const [selectedRouteId, setSelectedRouteId] = useState("");
  const [queue, setQueue] = useState<OfflineItem[]>([]);
  const [syncResults, setSyncResults] = useState<OWKSSyncResult[]>([]);
  const [challenge, setChallenge] = useState<{ id: string; expires_at: string } | null>(null);
  const [oneTimeCredential, setOneTimeCredential] = useState("");
  const [scanCredential, setScanCredential] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [isOnline, setIsOnline] = useState(
    () => typeof navigator === "undefined" || navigator.onLine,
  );
  const canWrite = user.permissions.includes("owks.write") || user.permissions.includes("owks.manage");
  const canManage = user.permissions.includes("owks.manage");
  const canCreateIncident = user.permissions.includes("incidents.create");

  const loadObjectData = useCallback(async (objectId: string) => {
    if (!objectId) return;
    try {
      const [nextEvents, nextPoints, nextRoutes, nextHandovers] = await Promise.all([
        getOWKSEvents(objectId),
        getOWKSControlPoints(objectId),
        getOWKSRoutes(objectId),
        getOWKSShiftHandovers(objectId),
      ]);
      setEvents(nextEvents);
      setPoints(nextPoints);
      setRoutes(nextRoutes);
      setHandovers(nextHandovers);
      setError("");
      if (canWrite) {
        setHandoverContext(await getOWKSShiftHandoverContext(objectId));
      } else {
        setHandoverContext(null);
      }
      if (canCreateIncident) {
        try {
          const choices = await getIncidentChoices(objectId);
          setIncidentChoices(choices);
        } catch (reason) {
          setIncidentChoices(null);
          setError(messageFrom(reason));
        }
      } else {
        setIncidentChoices(null);
      }
    } catch (reason) {
      setError(messageFrom(reason));
    }
  }, [canCreateIncident, canWrite]);

  useEffect(() => {
    getOWKSObjects()
      .then((items) => {
        setObjects(items);
        setSelectedObjectId(items[0]?.id ?? "");
      })
      .catch((reason: unknown) => setError(messageFrom(reason)));
    try {
      const stored = localStorage.getItem(QUEUE_KEY);
      if (stored) {
        const parsed: unknown = JSON.parse(stored);
        if (!Array.isArray(parsed)) throw new Error("Die lokale OWKS-Warteschlange ist ungültig.");
        setQueue(parsed as OfflineItem[]);
      }
    } catch (reason) {
      setError(messageFrom(reason));
    }
  }, []);

  useEffect(() => {
    if (!initialEventId) return;
    getOWKSEvent(initialEventId)
      .then((event) => {
        setFocusedEvent(event);
        setSelectedObjectId(event.object_id);
      })
      .catch((reason: unknown) => setError(messageFrom(reason)));
  }, [initialEventId]);

  useEffect(() => {
    if (
      focusedEvent
      && focusedEvent.object_id === selectedObjectId
      && !events.some((event) => event.id === focusedEvent.id)
    ) {
      setEvents((current) => [...current, focusedEvent]);
    }
  }, [events, focusedEvent, selectedObjectId]);

  useEffect(() => {
    if (selectedObjectId) void loadObjectData(selectedObjectId);
    setSelectedRouteId("");
    setChallenge(null);
    setScanCredential("");
  }, [loadObjectData, selectedObjectId]);

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  const selectedObject = useMemo(
    () => objects.find((item) => item.id === selectedObjectId),
    [objects, selectedObjectId],
  );

  function saveQueue(items: OfflineItem[]) {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(items));
    setQueue(items);
  }

  async function submitEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedObjectId || !canWrite) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const item: NewOfflineItem = {
      object_id: selectedObjectId,
      event_type: String(form.get("event_type")) as Exclude<OfflineItem["event_type"], "control">,
      title: String(form.get("title")).trim(),
      description: String(form.get("description") ?? "").trim(),
      severity: String(form.get("severity")) as OfflineItem["severity"],
      occurred_at: new Date().toISOString(),
      client_event_id: crypto.randomUUID(),
    };
    setBusy(true);
    try {
      if (!isOnline) {
        saveQueue([...queue, item]);
        setNotice("Ereignis lokal gespeichert und wartet auf Synchronisierung.");
      } else {
        await createOWKSEvent(item);
        setNotice("Wachbucheintrag wurde gespeichert.");
        await loadObjectData(selectedObjectId);
      }
      formElement.reset();
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function submitHandover(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedObjectId || !canWrite || !handoverContext) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const shiftId = String(form.get("handover_shift_id") ?? "");
    const recipientId = String(form.get("handover_recipient_id") ?? "");
    const handoverText = String(form.get("handover_text") ?? "").trim();
    const items = handoverItems
      .map((item) => ({ ...item, text: item.text.trim() }))
      .filter((item) => item.text);
    if (!shiftId || !recipientId || !handoverText) {
      setError("Bitte eine Schicht, die übernehmende Person und einen Übergabetext auswählen.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const saved = await createOWKSShiftHandover(selectedObjectId, {
        shift_id: shiftId,
        recipient_employee_id: recipientId,
        handover_text: handoverText,
        structured_items: items,
      });
      setHandovers((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
      setHandoverItems([{ category: "other", text: "" }]);
      setNotice("Schichtübergabe wurde unveränderlich gespeichert und wartet auf die Bestätigung der übernehmenden Person.");
      formElement.reset();
      await loadObjectData(selectedObjectId);
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function confirmHandover(handover: OWKSShiftHandover) {
    setBusy(true);
    setError("");
    try {
      const confirmed = await confirmOWKSShiftHandover(
        handover.id,
        confirmationNotes[handover.id] ?? "",
      );
      setHandovers((current) => current.map((item) => item.id === confirmed.id ? confirmed : item));
      setNotice("Übernahme wurde bestätigt und unveränderlich protokolliert.");
      await loadObjectData(selectedObjectId);
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function synchronizeQueue() {
    if (!queue.length) return;
    setBusy(true);
    setError("");
    try {
      const results = await syncOWKSEvents(queue);
      setSyncResults(results);
      const finished = new Set(
        results
          .filter((result) => result.status === "synced" || result.status === "duplicate")
          .map((result) => result.client_event_id),
      );
      saveQueue(queue.filter((item) => !finished.has(item.client_event_id)));
      setNotice("Synchronisierung abgeschlossen. Nicht verifizierte Kontrollen bleiben als Konflikt sichtbar.");
      await loadObjectData(selectedObjectId);
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function addControlPoint(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setBusy(true);
    try {
      const point = await createOWKSControlPoint(selectedObjectId, {
        name: String(form.get("point_name")),
        identifier_type: String(form.get("identifier_type")) as "qr" | "nfc",
      });
      setOneTimeCredential(point.credential ?? "");
      setNotice("Kontrollpunkt angelegt. Den QR-/NFC-Schlüssel jetzt sicher hinterlegen; er wird nur einmal angezeigt.");
      formElement.reset();
      await loadObjectData(selectedObjectId);
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function addRoute(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const pointIds = form.getAll("control_point_ids").map(String);
    setBusy(true);
    try {
      await createOWKSRoute(selectedObjectId, {
        name: String(form.get("route_name")),
        interval_minutes: Number(form.get("interval_minutes")),
        control_point_ids: pointIds,
      });
      setNotice("Kontrollroute wurde gespeichert.");
      formElement.reset();
      await loadObjectData(selectedObjectId);
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function beginScan() {
    setBusy(true);
    try {
      const result = await createOWKSChallenge(selectedObjectId);
      setChallenge(result);
      setNotice(`Kontrollanforderung gültig bis ${new Date(result.expires_at).toLocaleTimeString("de-DE")}.`);
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function verifyScan(credential: string) {
    if (!challenge) return;
    setBusy(true);
    try {
      await recordOWKSScan({
        challenge_id: challenge.id,
        credential,
        client_event_id: crypto.randomUUID(),
        ...(selectedRouteId ? { route_id: selectedRouteId } : {}),
      });
      setChallenge(null);
      setScanCredential("");
      setNotice("Kennung vom Server abgeglichen und protokolliert. Die physische Anwesenheit bleibt unbestätigt.");
      await loadObjectData(selectedObjectId);
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function submitScan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await verifyScan(scanCredential);
  }

  async function updateStatus(eventId: string, status: "open" | "in_progress" | "resolved") {
    setBusy(true);
    try {
      await updateOWKSEventStatus(eventId, status);
      await loadObjectData(selectedObjectId);
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function monitor(routeId: string) {
    setBusy(true);
    try {
      const missed = await monitorOWKSRoute(routeId);
      setNotice(missed.length
        ? `${missed.length} versäumte Kontrolle(n) wurden protokolliert.`
        : "Keine neuen versäumten Kontrollen.");
      await loadObjectData(selectedObjectId);
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function attachFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const selectedEventId = String(form.get("event_id"));
    const file = form.get("document");
    if (!(file instanceof File) || !file.size) {
      setError("Bitte eine PDF-, PNG- oder JPEG-Datei auswählen.");
      return;
    }
    setBusy(true);
    try {
      const saved = await uploadOWKSAttachment(selectedEventId, file);
      setAttachments((current) => ({
        ...current,
        [selectedEventId]: [...(current[selectedEventId] ?? []), saved],
      }));
      setNotice(`Anlage ${saved.file_name} wurde geschützt gespeichert.`);
      formElement.reset();
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function submitIncident(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!incidentEvent || !canCreateIncident) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const title = String(form.get("incident_title") ?? "").trim();
    const report = String(form.get("incident_report") ?? "").trim();
    const assignedToId = String(form.get("assigned_to_id") ?? "").trim();
    if (!title || !report || !assignedToId) {
      setError("Bitte Titel und Bericht ausfüllen und eine verantwortliche Person auswählen.");
      return;
    }
    if (!incidentChoices?.assignees.some((assignee) => assignee.id === assignedToId)) {
      setError("Die ausgewählte verantwortliche Person ist für dieses Objekt nicht verfügbar.");
      return;
    }
    const due = String(form.get("incident_due_at") ?? "");
    const dueAt = due ? new Date(due) : null;
    if (dueAt && Number.isNaN(dueAt.getTime())) {
      setError("Das Fälligkeitsdatum ist ungültig.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await createIncident({
        title,
        report,
        incident_type: String(form.get("incident_type")) as IncidentType,
        severity: String(form.get("incident_severity")) as IncidentSeverity,
        object_id: incidentEvent.object_id,
        assigned_to_id: assignedToId,
        due_at: dueAt?.toISOString(),
        owks_event_id: incidentEvent.id,
      });
      setIncidentChoices((current) => current && ({
        ...current,
        linked_owks_event_ids: [...current.linked_owks_event_ids, incidentEvent.id],
      }));
      setIncidentEvent(null);
      setNotice("Vorfall wurde angelegt und mit dem OWKS-Ereignis verknüpft.");
      formElement.reset();
    } catch (reason) {
      if (
        reason instanceof Error
        && reason.message === "Dieses OWKS-Ereignis ist bereits mit einem Vorgang verknüpft."
      ) {
        setIncidentChoices((current) => current && ({
          ...current,
          linked_owks_event_ids: [...current.linked_owks_event_ids, incidentEvent.id],
        }));
        setIncidentEvent(null);
      }
      setError(incidentMessageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  function removeConflict(clientEventId: string) {
    saveQueue(queue.filter((item) => item.client_event_id !== clientEventId));
  }

  async function toggleAttachments(eventId: string) {
    if (attachmentsOpen.includes(eventId)) {
      setAttachmentsOpen(attachmentsOpen.filter((id) => id !== eventId));
      return;
    }
    if (attachments[eventId]) {
      setAttachmentsOpen([...attachmentsOpen, eventId]);
      return;
    }
    try {
      const items = await getOWKSAttachments(eventId);
      setAttachments((current) => ({ ...current, [eventId]: items }));
      setAttachmentsOpen([...attachmentsOpen, eventId]);
    } catch (reason) {
      setError(messageFrom(reason));
    }
  }

  return (
    <section className="owks-module">
      <header className="object-intro">
        <p className="eyebrow">OPERATIVER EINSATZ</p>
        <h1>Online-Wachbuch</h1>
        <p className="muted">Objektbezogene Schichtübergaben, Ereignisse und nachvollziehbare Kontrollgänge.</p>
      </header>
      {error && <p className="alert page-alert" role="alert">{error}</p>}
      {notice && <p className="owks-notice" role="status">{notice}</p>}
      {selectedObject && <div className="panel owks-object-picker">
        <label>Objekt
          <select
            value={selectedObjectId}
            onChange={(event) => {
              setIncidentEvent(null);
              setIncidentChoices(null);
              setSelectedObjectId(event.target.value);
            }}
          >
            {objects.map((item) => <option key={item.id} value={item.id}>{item.code} – {item.name}</option>)}
          </select>
        </label>
      </div>}
      {!objects.length && <section className="panel"><p className="empty">Keine zugewiesenen aktiven Objekte verfügbar.</p></section>}

      {selectedObject && <>
        {canWrite && <section className="panel owks-panel">
          <div className="panel-heading"><div><p className="eyebrow">WACHBUCH</p><h2>Eintrag und Schichtübergabe</h2></div></div>
          <form className="owks-event-form" onSubmit={(event) => void submitEvent(event)}>
            <label>Art
              <select name="event_type">
                <option value="entry">Ereignis</option>
                <option value="handover">Schichtübergabe</option>
                <option value="deviation">Abweichung</option>
                <option value="notification">Meldung an Einsatzleitung</option>
                <option value="manipulation">Manipulationsverdacht</option>
              </select>
            </label>
            <label>Dringlichkeit
              <select name="severity"><option value="info">Information</option><option value="warning">Warnung</option><option value="critical">Kritisch</option></select>
            </label>
            <label>Titel<input name="title" required maxLength={200} /></label>
            <label>Beschreibung<textarea name="description" maxLength={10000} /></label>
            <button className="primary-button" disabled={busy}>Eintrag speichern</button>
          </form>
        </section>}

        {canWrite && <section className="panel owks-panel">
          <div className="panel-heading"><div><p className="eyebrow">SCHICHTWECHSEL</p><h2>Übergabe erstellen</h2></div></div>
          {handoverContext?.shifts.length && handoverContext.recipients.length
            ? <form className="owks-event-form" onSubmit={(event) => void submitHandover(event)}>
              <label>Eigene veröffentlichte Schicht
                <select name="handover_shift_id" required defaultValue="">
                  <option value="" disabled>Bitte Schicht auswählen</option>
                  {handoverContext.shifts.map((shift) => <option key={shift.id} value={shift.id}>
                    {new Date(shift.starts_at).toLocaleString("de-DE")} – {new Date(shift.ends_at).toLocaleTimeString("de-DE")}
                  </option>)}
                </select>
              </label>
              <label>Übernehmende Person
                <select name="handover_recipient_id" required defaultValue="">
                  <option value="" disabled>Bitte auswählen</option>
                  {handoverContext.recipients.map((recipient) =>
                    <option key={recipient.id} value={recipient.id}>{recipient.full_name}</option>,
                  )}
                </select>
              </label>
              <label>Übergabetext<textarea name="handover_text" required maxLength={10000} /></label>
              <fieldset className="owks-event-form">
                <legend>Strukturierte Übergabepunkte</legend>
                {handoverItems.map((item, index) => <div className="time-action-row" key={`handover-item-${index}`}>
                  <label>Kategorie
                    <select
                      aria-label={`Kategorie Übergabepunkt ${index + 1}`}
                      value={item.category}
                      onChange={(change) => setHandoverItems((current) => current.map((entry, itemIndex) =>
                        itemIndex === index
                          ? { ...entry, category: change.target.value as OWKSHandoverCategory }
                          : entry,
                      ))}
                    >
                      {HANDOVER_CATEGORIES.map((category) =>
                        <option key={category.value} value={category.value}>{category.label}</option>,
                      )}
                    </select>
                  </label>
                  <label>Hinweis
                    <input
                      aria-label={`Text Übergabepunkt ${index + 1}`}
                      maxLength={500}
                      value={item.text}
                      onChange={(change) => setHandoverItems((current) => current.map((entry, itemIndex) =>
                        itemIndex === index ? { ...entry, text: change.target.value } : entry,
                      ))}
                    />
                  </label>
                  {handoverItems.length > 1 && <button
                    type="button"
                    className="text-button"
                    onClick={() => setHandoverItems((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                  >Punkt entfernen</button>}
                </div>)}
                <button
                  type="button"
                  className="secondary-button"
                  disabled={handoverItems.length >= 50}
                  onClick={() => setHandoverItems((current) => [...current, { category: "other", text: "" }])}
                >Übergabepunkt ergänzen</button>
              </fieldset>
              <div>
                <h3>Automatisch übernommene offene Punkte</h3>
                {handoverContext.source_items.length
                  ? <ul>{handoverContext.source_items.map((source) => <li key={`${source.source_type}-${source.source_id}`}>
                    {handoverSourceSummary(source)}
                  </li>)}</ul>
                  : <p className="muted">Keine offenen relevanten Punkte mit den vorhandenen Leseberechtigungen.</p>}
                <p className="muted">Die Herkunft und der Stand zum Erstellungszeitpunkt werden mit der Übergabe gespeichert.</p>
              </div>
              <button className="primary-button" disabled={busy}>Übergabe speichern</button>
            </form>
            : <p className="muted">Eine Übergabe ist nur mit eigener veröffentlichter Schicht und einer aktiven, dem Objekt zugewiesenen übernehmenden Person möglich.</p>}
        </section>}

        {canWrite && <section className="panel owks-panel">
          <div className="panel-heading"><div><p className="eyebrow">QR / NFC</p><h2>Kontrollgang</h2></div></div>
          <p className="muted" role="note">
            {supportsWebNfc()
              ? "Web-NFC und QR-Kamera können direkt genutzt werden. Der Server prüft Kennung, Challenge und Objekt; ein statischer QR-/NFC-Tag beweist keine physische Anwesenheit."
              : "Web-NFC ist in diesem Browser/Gerät oder ohne sicheren Kontext nicht verfügbar. Nutzen Sie QR-Scan über HTTPS/lokal oder die manuelle Kennungseingabe."}
          </p>
          {!challenge
            ? <button className="secondary-button" disabled={busy} onClick={() => void beginScan()}>Kontrollanforderung starten</button>
            : <form className="owks-event-form" onSubmit={(event) => void submitScan(event)}>
              <p>Frische Kontrollanforderung aktiv. Sie können QR-Kamera, Web-NFC oder die manuelle Eingabe verwenden:</p>
              <OWKSScanTools
                disabled={busy}
                onDetected={(credential) => {
                  setScanCredential(credential);
                  void verifyScan(credential);
                }}
              />
              {routes.length > 0 && <label>Kontrollroute (optional)
                <select
                  value={selectedRouteId}
                  onChange={(event) => setSelectedRouteId(event.target.value)}
                >
                  <option value="">Keine Route zuordnen</option>
                  {routes.map((route) => <option key={route.id} value={route.id}>{route.name}</option>)}
                </select>
              </label>}
              <label>QR-/NFC-Kennung<input
                name="credential"
                required
                autoComplete="off"
                value={scanCredential}
                onChange={(event) => setScanCredential(event.target.value)}
              /></label>
              <div className="time-action-row">
                <button className="primary-button" disabled={busy}>Kontrolle verifizieren</button>
                <button type="button" className="secondary-button" onClick={() => setChallenge(null)}>Abbrechen</button>
              </div>
            </form>}
          {oneTimeCredential && <div className="owks-secret" role="status">
            <strong>Einmaliger Kontrollpunktschlüssel – sicher auf QR-Code oder NFC-Tag hinterlegen:</strong>
            <OWKSControlPointQr credential={oneTimeCredential} />
            <code>{oneTimeCredential}</code>
            <button className="text-button" onClick={() => setOneTimeCredential("")}>Anzeige schließen</button>
          </div>}
          <div className="owks-offline">
            <div><strong>Offline-Warteschlange</strong><span>{queue.length} ausstehend</span></div>
            <button className="secondary-button" disabled={busy || !queue.length || !isOnline} onClick={() => void synchronizeQueue()}>
              Warteschlange synchronisieren
            </button>
            {syncResults.filter((item) => item.status === "conflict").map((item) =>
              <div className="owks-conflict" key={item.client_event_id}>
                <strong>Konflikt – manuelle Prüfung erforderlich</strong>
                <p>{item.detail ?? item.event?.title}</p>
                <button className="text-button" onClick={() => removeConflict(item.client_event_id)}>Nach Prüfung aus lokaler Warteschlange entfernen</button>
              </div>,
            )}
            {queue.map((item) => <div className="owks-conflict" key={item.client_event_id}>
              <strong>{item.event_type === "control" ? "Offline-Kontrolle nicht verifiziert" : "Synchronisierung ausstehend"}</strong>
              <p>{item.title}</p>
              <button className="text-button" onClick={() => removeConflict(item.client_event_id)}>Aus lokaler Warteschlange entfernen</button>
            </div>)}
          </div>
        </section>}

        {canManage && <section className="owks-lower">
          <section className="panel">
            <div className="panel-heading"><div><p className="eyebrow">KONFIGURATION</p><h2>Kontrollpunkte und Routen</h2></div></div>
            <form className="owks-event-form" onSubmit={(event) => void addControlPoint(event)}>
              <label>Kontrollpunktname<input name="point_name" required maxLength={160} /></label>
              <label>Identifikation<select name="identifier_type"><option value="qr">QR-Code</option><option value="nfc">NFC</option></select></label>
              <button className="secondary-button" disabled={busy}>Kontrollpunkt anlegen</button>
            </form>
            <ul className="owks-point-list">{points.map((point) =>
              <li key={point.id}><strong>{point.name}</strong><span>{point.identifier_type.toUpperCase()}</span></li>,
            )}</ul>
            {points.length > 0 && <form className="owks-event-form owks-route-form" onSubmit={(event) => void addRoute(event)}>
              <h3>Route anlegen</h3>
              <label>Routenname<input name="route_name" required maxLength={160} /></label>
              <label>Kontrollintervall (Minuten)<input name="interval_minutes" type="number" min={1} max={1440} defaultValue={60} required /></label>
              <label>Reihenfolge der Kontrollpunkte
                <select name="control_point_ids" multiple required size={Math.min(points.length, 5)}>
                  {points.map((point) => <option key={point.id} value={point.id}>{point.name}</option>)}
                </select>
              </label>
              <button className="secondary-button" disabled={busy}>Route speichern</button>
            </form>}
            {routes.map((route) => <div className="owks-route-card" key={route.id}>
              <strong>{route.name}</strong><span>alle {route.interval_minutes} Minuten</span>
              <button className="text-button" disabled={busy} onClick={() => void monitor(route.id)}>Kontrollen auf Versäumnisse prüfen</button>
            </div>)}
          </section>
          {canWrite && events.length > 0 && <section className="panel">
            <div className="panel-heading"><div><p className="eyebrow">SICHERE ABLAGE</p><h2>Foto oder Dokument anhängen</h2></div></div>
            <form className="owks-event-form" onSubmit={(event) => void attachFile(event)}>
              <label>Wachbucheintrag<select name="event_id" required>{events.map((item) =>
                <option key={item.id} value={item.id}>{item.title}</option>,
              )}</select></label>
              <label>Datei (PDF, PNG, JPEG; max. 10 MiB)<input name="document" type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" required /></label>
              <button className="secondary-button" disabled={busy}>Geschützt speichern</button>
            </form>
          </section>}
        </section>}

        <section className="panel owks-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">ÜBERGABEVERLAUF</p><h2>Schichtübergaben</h2></div>
            <span className="result-count">{handovers.filter((item) => item.status === "pending").length} offen</span>
          </div>
          {!handovers.length && <p className="empty">Für dieses Objekt liegen noch keine Schichtübergaben vor.</p>}
          <div className="owks-event-list">{handovers.map((handover) => <article className="owks-event" key={handover.id}>
            <div className="owks-event-heading">
              <strong>{handover.sender_name} → {handover.recipient_name}</strong>
              <time>{new Date(handover.created_at).toLocaleString("de-DE")}</time>
            </div>
            <p>{handover.handover_text}</p>
            <div className="owks-event-meta">
              <span>{handover.status === "pending" ? "Bestätigung ausstehend – Leitstelle sichtbar" : "Übernahme bestätigt"}</span>
              <span>
                Schicht {new Date(handover.shift_starts_at).toLocaleString("de-DE")}
                – {new Date(handover.shift_ends_at).toLocaleString("de-DE")}
              </span>
            </div>
            {handover.structured_items.length > 0 && <ul>
              {handover.structured_items.map((item, index) => <li key={`${handover.id}-item-${index}`}>
                <strong>{HANDOVER_CATEGORIES.find((category) => category.value === item.category)?.label ?? item.category}:</strong> {item.text}
              </li>)}
            </ul>}
            {handover.source_items.length > 0 && <div>
              <h3>Übernommene offene Punkte</h3>
              <ul>{handover.source_items.map((source) => <li key={`${source.source_type}-${source.source_id}`}>
                {handoverSourceSummary(source)}
              </li>)}</ul>
            </div>}
            <ol aria-label="Änderungsverlauf">
              {handover.history.map((entry, index) => <li key={`${handover.id}-history-${index}`}>
                {entry.action === "submitted" ? "Übergeben" : "Übernahme bestätigt"} · {new Date(entry.occurred_at).toLocaleString("de-DE")}
                {entry.note && ` · ${entry.note}`}
              </li>)}
            </ol>
            {handover.status === "pending"
              && handoverContext?.current_employee_id === handover.recipient_employee_id
              && <div className="owks-event-form">
                <label>Bestätigungsnotiz (optional)
                  <textarea
                    maxLength={1000}
                    value={confirmationNotes[handover.id] ?? ""}
                    onChange={(change) => setConfirmationNotes((current) => ({
                      ...current,
                      [handover.id]: change.target.value,
                    }))}
                  />
                </label>
                <button className="primary-button" disabled={busy} onClick={() => void confirmHandover(handover)}>
                  Übergabe geprüft und übernommen
                </button>
              </div>}
          </article>)}</div>
        </section>

        <section className="panel owks-panel">
          <div className="panel-heading"><div><p className="eyebrow">APPEND-ONLY-PROTOKOLL</p><h2>Wachbuchereignisse</h2></div><span className="result-count">{events.length} Einträge</span></div>
          {!events.length && <p className="empty">Für dieses Objekt liegen noch keine Wachbuchereignisse vor.</p>}
          <div className="owks-event-list">{events.map((item) => <article
            className={`owks-event owks-severity-${item.severity}${item.id === focusedEvent?.id ? " search-result-row" : ""}`}
            key={item.id}
          >
            <div className="owks-event-heading"><strong>{item.title}</strong><time>{new Date(item.occurred_at).toLocaleString("de-DE")}</time></div>
            <p>{item.description || "Keine zusätzliche Beschreibung."}</p>
            <div className="owks-event-meta">
              <span>{item.event_type}</span><span>Status: {item.status}</span>
              {item.event_type === "control" && !item.presence_verified && <span className="owks-conflict-label">Physische Anwesenheit nicht bestätigt</span>}
              {item.sync_status === "conflict" && <span className="owks-conflict-label">Synchronisierungskonflikt</span>}
              {item.corrects_event_id && <span>Korrektur eines älteren Eintrags</span>}
            </div>
            {canCreateIncident
              && incidentChoices?.objects.some((object) => object.id === item.object_id)
              && item.object_id === selectedObjectId
              && (incidentChoices.linked_owks_event_ids.includes(item.id)
                ? <p className="muted" role="status">Bereits mit einem Vorgang verknüpft</p>
                : <div className="time-action-row">
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => {
                    setIncidentEvent(incidentEvent?.id === item.id ? null : item);
                    setError("");
                  }}
                >
                  {incidentEvent?.id === item.id ? "Erfassung abbrechen" : "Als Vorfall erfassen"}
                </button>
              </div>)}
            {incidentEvent?.id === item.id && <form
              className="owks-event-form"
              onSubmit={(event) => void submitIncident(event)}
            >
              <p className="muted">Das OWKS-Original bleibt unverändert. Nur der Ereignisbezug wird gespeichert; sensible Angaben oder Anlagen werden nicht übernommen.</p>
              <label>Titel<input name="incident_title" required maxLength={200} /></label>
              <label>Typ
                <select name="incident_type" defaultValue="incident">
                  <option value="incident">Vorfall</option>
                  <option value="complaint">Beschwerde</option>
                  <option value="other">Sonstiges</option>
                </select>
              </label>
              <label>Schwere
                <select name="incident_severity" defaultValue="medium">
                  <option value="low">Niedrig</option>
                  <option value="medium">Mittel</option>
                  <option value="high">Hoch</option>
                  <option value="critical">Kritisch</option>
                </select>
              </label>
              <label>Bericht<textarea name="incident_report" required maxLength={4000} /></label>
              <label>Verantwortliche Person
                <select name="assigned_to_id" required defaultValue="">
                  <option value="" disabled>Bitte auswählen</option>
                  {(incidentChoices?.assignees ?? []).map((assignee) =>
                    <option key={assignee.id} value={assignee.id}>{assignee.full_name}</option>,
                  )}
                </select>
              </label>
              {!incidentChoices?.assignees.length
                && <p className="muted">Für dieses Objekt sind keine verfügbaren Verantwortlichen vorhanden.</p>}
              <label>Fällig am (optional)<input name="incident_due_at" type="datetime-local" /></label>
              <div className="time-action-row">
                <button className="primary-button" disabled={busy || !incidentChoices?.assignees.length}>
                  Vorfall anlegen
                </button>
                <button
                  type="button"
                  className="text-button"
                  disabled={busy}
                  onClick={() => setIncidentEvent(null)}
                >Abbrechen</button>
              </div>
            </form>}
            {canManage && <div className="time-action-row">
              {item.status !== "in_progress" && <button className="text-button" onClick={() => void updateStatus(item.id, "in_progress")}>In Bearbeitung</button>}
              {item.status !== "resolved" && <button className="text-button" onClick={() => void updateStatus(item.id, "resolved")}>Als erledigt markieren</button>}
            </div>}
            <div className="owks-event-attachments">
              <button className="text-button" onClick={() => void toggleAttachments(item.id)}>
                {attachmentsOpen.includes(item.id) ? "Anlagen ausblenden" : "Anlagen anzeigen"}
              </button>
              {attachmentsOpen.includes(item.id) && <ul>
                {(attachments[item.id] ?? []).map((attachment) => <li key={attachment.id}>
                  <a
                    href={owksAttachmentUrl(item.id, attachment.id)}
                    target="_blank"
                    rel="noreferrer"
                  >{attachment.file_name}</a>
                  {" · "}
                  <a href={owksAttachmentUrl(item.id, attachment.id, true)}>
                    Herunterladen
                  </a>
                </li>)}
                {!attachments[item.id]?.length && <li className="muted">Keine Anlagen gespeichert.</li>}
              </ul>}
            </div>
          </article>)}</div>
        </section>
      </>}
    </section>
  );
}
