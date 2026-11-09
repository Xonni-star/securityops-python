import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  archiveInventoryAsset,
  createInventoryAsset,
  createInventoryEvent,
  getInventoryAssets,
  getInventoryEligibleEmployees,
  getInventoryEmployees,
  getInventoryEvents,
  getInventoryObjects,
  updateInventoryAsset,
} from "./api";
import type {
  InventoryActionType,
  InventoryAsset,
  InventoryCategory,
  InventoryCondition,
  InventoryEmployeeCandidate,
  InventoryEvent,
  InventoryObjectCandidate,
  InventoryStatus,
} from "./types";

const pageSize = 25;

const categoryNames: Record<InventoryCategory, string> = {
  access_media: "Schließ- und Zutrittsmedien",
  radio: "Funkgeräte",
  smartphone: "Smartphones",
  tablet: "Tablets",
  computer: "Computer",
  clothing: "Dienstkleidung",
  safety_equipment: "Sicherheitsausrüstung",
  vehicle: "Fahrzeuge",
  other: "Sonstige Betriebsmittel",
};

const conditionNames: Record<InventoryCondition, string> = {
  new: "Neu",
  good: "Gut",
  used: "Gebraucht",
  worn: "Abgenutzt",
  defective: "Defekt",
};

const statusNames: Record<InventoryStatus, string> = {
  available: "Verfügbar",
  issued: "Ausgegeben",
  maintenance: "In Wartung",
  lost: "Verloren",
  damaged: "Beschädigt",
  archived: "Archiviert",
};

const eventNames: Record<InventoryActionType, string> = {
  issued: "Ausgabe",
  returned: "Rückgabe",
  transferred: "Übergabe",
  lost: "Verlustmeldung",
  damaged: "Beschädigung melden",
  maintenance: "Wartung aufnehmen",
  repair: "Reparatur abschließen",
};

function messageFrom(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString("de-DE");
}

export default function InventoryManagement({
  canManage,
  canManageGlobal,
  canMove,
}: {
  canManage: boolean;
  canManageGlobal: boolean;
  canMove: boolean;
}) {
  const [items, setItems] = useState<InventoryAsset[]>([]);
  const [objects, setObjects] = useState<InventoryObjectCandidate[]>([]);
  const [inventoryEmployees, setInventoryEmployees] = useState<InventoryEmployeeCandidate[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<InventoryCategory | "">("");
  const [condition, setCondition] = useState<InventoryCondition | "">("");
  const [assetStatus, setAssetStatus] = useState<InventoryStatus | "">("");
  const [objectId, setObjectId] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [createObjectId, setCreateObjectId] = useState("");
  const [editingAsset, setEditingAsset] = useState<InventoryAsset | null>(null);
  const [eventAsset, setEventAsset] = useState<InventoryAsset | null>(null);
  const [eventType, setEventType] = useState<InventoryActionType>("issued");
  const [eventObjectId, setEventObjectId] = useState("");
  const [employees, setEmployees] = useState<InventoryEmployeeCandidate[]>([]);
  const [expandedAssetId, setExpandedAssetId] = useState("");
  const [history, setHistory] = useState<Record<string, InventoryEvent[]>>({});

  const loadInventory = useCallback(async () => {
    setLoading(true);
    try {
      const [page, objectOptions, employeeOptions] = await Promise.all([
        getInventoryAssets({
          q: query,
          category,
          condition,
          status: assetStatus,
          object_id: objectId,
          employee_id: employeeId,
          include_archived: includeArchived,
          limit: pageSize,
          offset,
        }),
        getInventoryObjects(),
        getInventoryEmployees(),
      ]);
      setItems(page.items);
      setTotal(page.total);
      setObjects(objectOptions);
      setInventoryEmployees(employeeOptions);
      if (!canManageGlobal && objectOptions.length) {
        setCreateObjectId((current) => current || objectOptions[0].id);
      }
      setError("");
    } catch (reason) {
      setError(messageFrom(reason, "Inventar konnte nicht geladen werden."));
    } finally {
      setLoading(false);
    }
  }, [
    assetStatus,
    canManageGlobal,
    category,
    condition,
    employeeId,
    includeArchived,
    objectId,
    offset,
    query,
  ]);

  useEffect(() => {
    void loadInventory();
  }, [loadInventory]);

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await createInventoryAsset({
        asset_number: String(data.get("asset_number") ?? "").trim(),
        serial_number: String(data.get("serial_number") ?? "").trim() || undefined,
        name: String(data.get("name") ?? "").trim(),
        category: String(data.get("category") ?? "other") as InventoryCategory,
        condition: String(data.get("condition") ?? "good") as InventoryCondition,
        location: String(data.get("location") ?? "").trim(),
        object_id: String(data.get("object_id") ?? "") || undefined,
      });
      setShowCreate(false);
      setOffset(0);
      await loadInventory();
    } catch (reason) {
      setError(messageFrom(reason, "Inventargegenstand konnte nicht angelegt werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingAsset) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await updateInventoryAsset(editingAsset.id, {
        serial_number: String(data.get("serial_number") ?? "").trim() || null,
        name: String(data.get("name") ?? "").trim(),
        category: String(data.get("category") ?? "other") as InventoryCategory,
        condition: String(data.get("condition") ?? "good") as InventoryCondition,
        location: String(data.get("location") ?? "").trim(),
      });
      setEditingAsset(null);
      await loadInventory();
    } catch (reason) {
      setError(messageFrom(reason, "Inventarstammdaten konnten nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function startEvent(asset: InventoryAsset, type: InventoryActionType) {
    setEventAsset(asset);
    setEventType(type);
    setEventObjectId(asset.object_id ?? "");
    setEmployees([]);
    if (type !== "issued" && type !== "transferred") return;
    try {
      setEmployees(await getInventoryEligibleEmployees(asset.object_id ?? undefined));
    } catch (reason) {
      setError(messageFrom(reason, "Zugeordnete Mitarbeiter konnten nicht geladen werden."));
    }
  }

  async function submitEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!eventAsset) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await createInventoryEvent(eventAsset.id, {
        event_type: eventType,
        ...(eventType === "issued" || eventType === "transferred"
          ? {
            employee_id: String(data.get("employee_id") ?? ""),
            acknowledged: data.get("acknowledged") === "on",
            acknowledgement_note: String(data.get("acknowledgement_note") ?? "").trim() || undefined,
          }
          : {}),
        ...(eventType === "transferred" && eventObjectId !== eventAsset.object_id
          ? { object_id: eventObjectId || null }
          : {}),
        ...(eventType === "repair"
          ? { condition: String(data.get("condition") ?? "good") as InventoryCondition }
          : {}),
        location: String(data.get("location") ?? "").trim() || undefined,
        note: String(data.get("note") ?? "").trim() || undefined,
      });
      setEventAsset(null);
      await loadInventory();
      if (expandedAssetId === eventAsset.id) await loadHistory(eventAsset.id);
    } catch (reason) {
      setError(messageFrom(reason, "Inventarvorgang konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function loadHistory(assetId: string) {
    try {
      const page = await getInventoryEvents(assetId);
      setHistory((current) => ({ ...current, [assetId]: page.items }));
    } catch (reason) {
      setError(messageFrom(reason, "Inventarhistorie konnte nicht geladen werden."));
    }
  }

  async function toggleHistory(assetId: string) {
    if (expandedAssetId === assetId) {
      setExpandedAssetId("");
      return;
    }
    setExpandedAssetId(assetId);
    await loadHistory(assetId);
  }

  async function handleArchive(asset: InventoryAsset) {
    setBusy(true);
    try {
      await archiveInventoryAsset(asset.id);
      await loadInventory();
    } catch (reason) {
      setError(messageFrom(reason, "Inventargegenstand konnte nicht archiviert werden."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="key-register inventory-register">
      <section className="panel" aria-labelledby="inventory-heading">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">BESTANDSVERWALTUNG</p>
            <h2 id="inventory-heading">Inventarverwaltung</h2>
          </div>
          <span className="result-count">{total} Gegenstände</span>
        </div>
        <p className="muted">
          Physische Schlüssel werden weiterhin im separaten Schlüsselregister verwaltet.
          Automatische Wartungsfristen oder Benachrichtigungen sind nicht eingerichtet.
        </p>
        {error && <p className="alert" role="alert">{error}</p>}
        <div className="key-filters">
          <label>
            Suche
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setOffset(0);
              }}
              maxLength={200}
              placeholder="Inventarnummer, Seriennummer oder Bezeichnung"
            />
          </label>
          <label>
            Kategorie
            <select value={category} onChange={(event) => {
              setCategory(event.target.value as InventoryCategory | "");
              setOffset(0);
            }}>
              <option value="">Alle Kategorien</option>
              {Object.entries(categoryNames).map(([value, name]) =>
                <option key={value} value={value}>{name}</option>)}
            </select>
          </label>
          <label>
            Zustand
            <select value={condition} onChange={(event) => {
              setCondition(event.target.value as InventoryCondition | "");
              setOffset(0);
            }}>
              <option value="">Alle Zustände</option>
              {Object.entries(conditionNames).map(([value, name]) =>
                <option key={value} value={value}>{name}</option>)}
            </select>
          </label>
          <label>
            Status
            <select value={assetStatus} onChange={(event) => {
              setAssetStatus(event.target.value as InventoryStatus | "");
              setOffset(0);
            }}>
              <option value="">Alle aktiven Status</option>
              {Object.entries(statusNames).map(([value, name]) =>
                <option key={value} value={value}>{name}</option>)}
            </select>
          </label>
          <label>
            Objekt
            <select value={objectId} onChange={(event) => {
              setObjectId(event.target.value);
              setOffset(0);
            }}>
              <option value="">Alle Objekte</option>
              {objects.map((obj) =>
                <option key={obj.id} value={obj.id}>{obj.code} · {obj.name}</option>)}
            </select>
          </label>
          <label>
            Mitarbeiter
            <select value={employeeId} onChange={(event) => {
              setEmployeeId(event.target.value);
              setOffset(0);
            }}>
              <option value="">Alle Mitarbeiter</option>
              {inventoryEmployees.map((employee) =>
                <option key={employee.id} value={employee.id}>
                  {employee.employee_number} · {employee.full_name}
                </option>)}
            </select>
          </label>
          <label className="key-archived-filter">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(event) => {
                setIncludeArchived(event.target.checked);
                setOffset(0);
              }}
            />
            Archivierte einbeziehen
          </label>
        </div>

        {canManage && <button className="primary-button" onClick={() => setShowCreate((value) => !value)}>
          {showCreate ? "Neuen Gegenstand schließen" : "Inventar erfassen"}
        </button>}
        {showCreate && canManage && <form className="key-form" onSubmit={(event) => void submitCreate(event)}>
          <h3>Inventargegenstand erfassen</h3>
          <div className="form-row">
            <label>Inventarnummer<input name="asset_number" required maxLength={80} /></label>
            <label>Seriennummer<input name="serial_number" maxLength={120} /></label>
          </div>
          <div className="form-row">
            <label>Bezeichnung<input name="name" required maxLength={200} /></label>
            <label>Kategorie<select name="category" defaultValue="other">
              {Object.entries(categoryNames).map(([value, name]) =>
                <option key={value} value={value}>{name}</option>)}
            </select></label>
          </div>
          <div className="form-row">
            <label>Zustand<select name="condition" defaultValue="good">
              {Object.entries(conditionNames).map(([value, name]) =>
                <option key={value} value={value}>{name}</option>)}
            </select></label>
            <label>Standort<input name="location" required maxLength={200} /></label>
          </div>
          <label>Objekt<select
            name="object_id"
            value={createObjectId}
            required={!canManageGlobal}
            onChange={(event) => setCreateObjectId(event.target.value)}
          >
            {canManageGlobal
              ? <option value="">Zentrales Inventar</option>
              : <option value="" disabled>Objekt auswählen</option>}
            {objects.map((obj) =>
              <option key={obj.id} value={obj.id}>{obj.code} · {obj.name}</option>)}
          </select></label>
          <button className="primary-button" disabled={busy}>
            {busy ? "Wird gespeichert …" : "Inventargegenstand speichern"}
          </button>
        </form>}

        {loading
          ? <p className="muted" role="status">Inventar wird geladen …</p>
          : items.length === 0
          ? <p className="empty">Keine Inventargegenstände für diese Auswahl vorhanden.</p>
          : <div className="key-list">
            {items.map((asset) => (
              <article className="key-card" key={asset.id}>
                <div className="key-card-heading">
                  <div>
                    <h3>{asset.asset_number}
                      <span className={`key-status key-status-${asset.status}`}>{statusNames[asset.status]}</span>
                    </h3>
                    <p>{asset.name} · {categoryNames[asset.category]}</p>
                    <p className="muted">
                      Zustand: {conditionNames[asset.condition]} · Standort: {asset.location}
                      {asset.serial_number ? ` · Seriennummer: ${asset.serial_number}` : ""}
                    </p>
                    <p className="muted">
                      {asset.object_code
                        ? `${asset.object_code} · ${asset.object_name}`
                        : "Zentrales Inventar"}
                      {asset.current_employee_name ? ` · bei ${asset.current_employee_name}` : ""}
                    </p>
                  </div>
                  <button className="secondary-button" onClick={() => void toggleHistory(asset.id)}>
                    {expandedAssetId === asset.id ? "Historie schließen" : "Historie"}
                  </button>
                </div>
                <div className="key-actions">
                  {canManage && asset.status !== "archived" && <>
                    <button className="secondary-button" onClick={() => setEditingAsset(asset)}>
                      Stammdaten ändern
                    </button>
                    {asset.status !== "issued" && asset.status !== "maintenance" &&
                      <button className="secondary-button" disabled={busy} onClick={() => void handleArchive(asset)}>
                        Archivieren
                      </button>}
                  </>}
                  {canMove && asset.status === "available" && <>
                    <button className="secondary-button" onClick={() => void startEvent(asset, "issued")}>Ausgeben</button>
                    <button className="secondary-button" onClick={() => void startEvent(asset, "maintenance")}>Wartung aufnehmen</button>
                    <button className="secondary-button" onClick={() => void startEvent(asset, "damaged")}>Beschädigung melden</button>
                    <button className="secondary-button" onClick={() => void startEvent(asset, "lost")}>Verlust melden</button>
                  </>}
                  {canMove && asset.status === "issued" && <>
                    <button className="secondary-button" onClick={() => void startEvent(asset, "returned")}>Rückgabe erfassen</button>
                    <button className="secondary-button" onClick={() => void startEvent(asset, "transferred")}>Übergabe erfassen</button>
                    <button className="secondary-button" onClick={() => void startEvent(asset, "damaged")}>Beschädigung melden</button>
                    <button className="secondary-button" onClick={() => void startEvent(asset, "lost")}>Verlust melden</button>
                  </>}
                  {canMove && ["maintenance", "damaged"].includes(asset.status) &&
                    <button className="secondary-button" onClick={() => void startEvent(asset, "repair")}>
                      Reparatur abschließen
                    </button>}
                </div>
                {editingAsset?.id === asset.id && <form className="key-form" onSubmit={(event) => void submitUpdate(event)}>
                  <h3>Stammdaten ändern · {asset.asset_number}</h3>
                  <div className="form-row">
                    <label>Seriennummer<input name="serial_number" defaultValue={asset.serial_number ?? ""} maxLength={120} /></label>
                    <label>Bezeichnung<input name="name" defaultValue={asset.name} required maxLength={200} /></label>
                  </div>
                  <div className="form-row">
                    <label>Kategorie<select name="category" defaultValue={asset.category}>
                      {Object.entries(categoryNames).map(([value, name]) =>
                        <option key={value} value={value}>{name}</option>)}
                    </select></label>
                    <label>Zustand<select name="condition" defaultValue={asset.condition}>
                      {Object.entries(conditionNames).map(([value, name]) =>
                        <option key={value} value={value}>{name}</option>)}
                    </select></label>
                  </div>
                  <label>Standort<input name="location" defaultValue={asset.location} required maxLength={200} /></label>
                  <button className="primary-button" disabled={busy}>Änderungen speichern</button>
                  <button type="button" className="secondary-button" onClick={() => setEditingAsset(null)}>Abbrechen</button>
                </form>}
                {eventAsset?.id === asset.id && <form className="key-form" onSubmit={(event) => void submitEvent(event)}>
                  <h3>{eventNames[eventType]} · {asset.asset_number}</h3>
                  {(eventType === "issued" || eventType === "transferred") && <>
                    {eventType === "transferred" && canManage &&
                      <label>Zielobjekt<select
                        value={eventObjectId}
                        onChange={(change) => {
                          const targetObjectId = change.target.value;
                          setEventObjectId(targetObjectId);
                          void getInventoryEligibleEmployees(targetObjectId || undefined)
                            .then(setEmployees)
                            .catch((reason: unknown) =>
                              setError(messageFrom(reason, "Zugeordnete Mitarbeiter konnten nicht geladen werden.")));
                        }}
                      >
                        {canManageGlobal && <option value="">Zentrales Inventar</option>}
                        {objects.map((obj) =>
                          <option key={obj.id} value={obj.id}>{obj.code} · {obj.name}</option>)}
                      </select></label>}
                    <label>Mitarbeiter<select name="employee_id" required defaultValue="">
                      <option value="" disabled>Mitarbeiter auswählen</option>
                      {employees.map((employee) =>
                        <option key={employee.id} value={employee.id}>
                          {employee.employee_number} · {employee.full_name}
                        </option>)}
                    </select></label>
                    {employees.length === 0 &&
                      <p className="muted">Für den Bereich sind keine aktiven Mitarbeiter mit Benutzerkonto verfügbar.</p>}
                    <label className="key-acknowledgement">
                      <input type="checkbox" name="acknowledged" required />
                      Empfang durch den ausgewählten Mitarbeiter bestätigt
                    </label>
                    <label>Quittierungsnotiz<input name="acknowledgement_note" maxLength={2000} /></label>
                  </>}
                  {eventType === "repair" && <label>Zustand nach der Reparatur<select name="condition" required defaultValue="">
                    <option value="" disabled>Zustand auswählen</option>
                    {Object.entries(conditionNames).map(([value, name]) =>
                      <option key={value} value={value}>{name}</option>)}
                  </select></label>}
                  {["lost", "damaged", "maintenance", "repair"].includes(eventType) &&
                    <label>Notiz<textarea name="note" required maxLength={5000} /></label>}
                  {["returned", "issued", "transferred"].includes(eventType) &&
                    <label>Notiz<textarea name="note" maxLength={5000} /></label>}
                  <label>Standort nach dem Vorgang<input name="location" maxLength={200} defaultValue={asset.location} /></label>
                  <button
                    className="primary-button"
                    disabled={busy || (["issued", "transferred"].includes(eventType) && employees.length === 0)}
                  >
                    {busy ? "Wird protokolliert …" : "Vorgang protokollieren"}
                  </button>
                  <button type="button" className="secondary-button" onClick={() => setEventAsset(null)}>Abbrechen</button>
                </form>}
                {expandedAssetId === asset.id && <div className="key-history">
                  <h4>Nachvollziehbare Historie</h4>
                  {(history[asset.id] ?? []).length === 0
                    ? <p className="empty">Noch keine Vorgänge protokolliert.</p>
                    : <ol>
                      {(history[asset.id] ?? []).map((entry) => <li key={entry.id}>
                        <strong>{eventNames[entry.event_type as InventoryActionType] ?? (
                          entry.event_type === "created" ? "Erfasst" :
                            entry.event_type === "updated" ? "Stammdaten geändert" : "Archiviert"
                        )}</strong>
                        <span>{formatDate(entry.created_at)} · {entry.actor_name}</span>
                        {(entry.from_employee_name || entry.to_employee_name) &&
                          <span>
                            {entry.from_employee_name ? `Von: ${entry.from_employee_name}` : ""}
                            {entry.from_employee_name && entry.to_employee_name ? " → " : ""}
                            {entry.to_employee_name ? `An: ${entry.to_employee_name}` : ""}
                          </span>}
                        {(entry.from_object_name || entry.to_object_name) &&
                          <span>
                            {entry.from_object_name ? `Objekt: ${entry.from_object_name}` : ""}
                            {entry.from_object_name && entry.to_object_name ? " → " : ""}
                            {entry.to_object_name ? `Objekt: ${entry.to_object_name}` : ""}
                          </span>}
                        <span>{statusNames[entry.status_after]} · {conditionNames[entry.condition_after]} · {entry.location_after}</span>
                        {entry.acknowledged_at && <span>Empfang quittiert: {formatDate(entry.acknowledged_at)}</span>}
                        {entry.acknowledgement_note && <span>Quittierungsnotiz: {entry.acknowledgement_note}</span>}
                        {entry.note && <span>Notiz: {entry.note}</span>}
                      </li>)}
                    </ol>}
                </div>}
              </article>
            ))}
          </div>}
        <div className="pagination">
          <span className="result-count">
            {total === 0 ? "0 Einträge" : `${offset + 1}–${Math.min(offset + pageSize, total)} von ${total}`}
          </span>
          <div>
            <button className="secondary-button" disabled={offset === 0 || loading} onClick={() => setOffset((value) => Math.max(0, value - pageSize))}>Zurück</button>
            <button className="secondary-button" disabled={offset + pageSize >= total || loading} onClick={() => setOffset((value) => value + pageSize)}>Weiter</button>
          </div>
        </div>
      </section>
    </section>
  );
}
