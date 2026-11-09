import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  archiveObject,
  createObject,
  createObjectContact,
  deleteObjectContact,
  getCustomers,
  getObject,
  getObjectAssignmentCandidates,
  getObjectAssignments,
  getObjectHistory,
  getObjects,
  getObjectSecurity,
  reactivateObject,
  updateObject,
  updateObjectAssignments,
  updateObjectContact,
  updateObjectSecurity,
} from "./api";
import type {
  AuthUser,
  Customer,
  ObjectAddress,
  ObjectAddressInput,
  ObjectAssignment,
  ObjectAssignmentCandidate,
  ObjectContact,
  ObjectHistory,
  ObjectSecurityDetails,
  ObjectSort,
  ObjectStatus,
  SecurityObject,
} from "./types";

const pageSize = 25;

const statusNames: Record<ObjectStatus, string> = {
  active: "Aktiv",
  inactive: "Inaktiv",
};

const actionNames: Record<string, string> = {
  created: "Objekt angelegt",
  updated: "Objektdaten geändert",
  archived: "Objekt archiviert",
  reactivated: "Objekt reaktiviert",
  contact_created: "Ansprechpartner hinzugefügt",
  contact_updated: "Ansprechpartner geändert",
  contact_deleted: "Ansprechpartner entfernt",
  assignments_updated: "Mitarbeiterzuweisungen geändert",
  security_updated: "Sicherheitsdaten geändert",
};

function messageFrom(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function optionalValue(data: FormData, name: string) {
  return String(data.get(name) ?? "").trim() || undefined;
}

function qualificationRequirements(data: FormData) {
  return String(data.get("qualification_requirements") ?? "")
    .split("\n")
    .map((value) => value.trim())
    .filter(Boolean);
}

function formAddress(data: FormData, prefix: string): ObjectAddressInput | undefined {
  const street = optionalValue(data, `${prefix}_street`);
  const houseNumber = optionalValue(data, `${prefix}_house_number`);
  const postalCode = optionalValue(data, `${prefix}_postal_code`);
  const city = optionalValue(data, `${prefix}_city`);
  if (!street && !houseNumber && !postalCode && !city) return undefined;
  if (!street || !houseNumber || !postalCode || !city) {
    throw new Error("Bitte fülle Straße, Hausnummer, PLZ und Ort vollständig aus.");
  }
  return {
    street,
    house_number: houseNumber,
    postal_code: postalCode,
    city,
    country_code: optionalValue(data, `${prefix}_country_code`)?.toUpperCase() || "DE",
  };
}

function AddressFields({
  prefix,
  address,
}: {
  prefix: string;
  address?: ObjectAddress | null;
}) {
  return (
    <fieldset className="address-fields">
      <legend>Objektanschrift</legend>
      <label>Straße<input name={`${prefix}_street`} defaultValue={address?.street ?? ""} maxLength={160} /></label>
      <div className="form-row">
        <label>Hausnummer<input name={`${prefix}_house_number`} defaultValue={address?.house_number ?? ""} maxLength={30} /></label>
        <label>PLZ<input name={`${prefix}_postal_code`} defaultValue={address?.postal_code ?? ""} maxLength={20} /></label>
      </div>
      <div className="form-row">
        <label>Ort<input name={`${prefix}_city`} defaultValue={address?.city ?? ""} maxLength={100} /></label>
        <label>Ländercode<input name={`${prefix}_country_code`} defaultValue={address?.country_code ?? "DE"} maxLength={2} /></label>
      </div>
    </fieldset>
  );
}

export default function ObjectManagement({
  user,
  initialObjectId,
  onInitialObjectOpened,
}: {
  user: AuthUser;
  initialObjectId: string | null;
  onInitialObjectOpened: () => void;
}) {
  const canRead = user.permissions.includes("objects.read");
  const canCreate = user.permissions.includes("objects.manage")
    && user.permissions.includes("objects.manage_all");
  const canManage = user.permissions.includes("objects.manage");
  const canManageAll = user.permissions.includes("objects.manage_all");
  const canAssign = user.permissions.includes("objects.assign");
  const canReadSensitive = user.permissions.includes("objects.sensitive.read");
  const canManageSensitive = user.permissions.includes("objects.sensitive.manage");
  const canReadCustomers = user.permissions.includes("customers.read");

  const [objects, setObjects] = useState<SecurityObject[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ObjectStatus | "">("");
  const [customerFilter, setCustomerFilter] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [sortBy, setSortBy] = useState<ObjectSort>("name");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<SecurityObject | null>(null);
  const [history, setHistory] = useState<ObjectHistory[]>([]);
  const [security, setSecurity] = useState<ObjectSecurityDetails | null>(null);
  const [assignments, setAssignments] = useState<ObjectAssignment[]>([]);
  const [assignmentCandidates, setAssignmentCandidates] = useState<ObjectAssignmentCandidate[]>([]);
  const [assignedUserIds, setAssignedUserIds] = useState<string[]>([]);
  const [securityForm, setSecurityForm] = useState({
    security_requirements: "",
    access_information: "",
    emergency_contact: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadObjects = useCallback(async () => {
    if (!canRead) return;
    try {
      const page = await getObjects({
        q: search,
        status: statusFilter,
        customerId: customerFilter,
        includeArchived,
        sortBy,
        sortOrder,
        limit: pageSize,
        offset,
      });
      setObjects(page.items);
      setTotal(page.total);
      setError("");
    } catch (reason) {
      setError(messageFrom(reason, "Objekte konnten nicht geladen werden."));
    }
  }, [canRead, customerFilter, includeArchived, offset, search, sortBy, sortOrder, statusFilter]);

  useEffect(() => {
    void loadObjects();
  }, [loadObjects]);

  useEffect(() => {
    if (!canReadCustomers) return;
    const loadCustomers = async () => {
      const allCustomers: Customer[] = [];
      let totalCustomers = 0;
      do {
        const page = await getCustomers({
          q: "",
          status: "",
          contractStatus: "",
          includeArchived: user.permissions.includes("customers.archive"),
          sortBy: "company_name",
          sortOrder: "asc",
          limit: 100,
          offset: allCustomers.length,
        });
        allCustomers.push(...page.items);
        totalCustomers = page.total;
        if (page.items.length === 0) break;
      } while (allCustomers.length < totalCustomers);
      setCustomers(allCustomers);
    };
    loadCustomers()
      .catch((reason) => setError(messageFrom(reason, "Kunden konnten nicht geladen werden.")));
  }, [canReadCustomers, user.permissions]);

  const refreshSelected = useCallback(async (objectId: string) => {
    const [object, objectHistory, securityDetails, objectAssignments, candidates] = await Promise.all([
      getObject(objectId),
      getObjectHistory(objectId),
      canReadSensitive ? getObjectSecurity(objectId) : Promise.resolve(null),
      canAssign ? getObjectAssignments(objectId) : Promise.resolve([]),
      canAssign ? getObjectAssignmentCandidates() : Promise.resolve([]),
    ]);
    setSelected(object);
    setHistory(objectHistory);
    setSecurity(securityDetails);
    setSecurityForm({
      security_requirements: securityDetails?.security_requirements ?? "",
      access_information: securityDetails?.access_information ?? "",
      emergency_contact: securityDetails?.emergency_contact ?? "",
    });
    setAssignments(objectAssignments);
    setAssignedUserIds(objectAssignments.map((assignment) => assignment.user_id));
    setAssignmentCandidates(candidates);
    return object;
  }, [canAssign, canReadSensitive]);

  useEffect(() => {
    if (!initialObjectId) return;
    let active = true;
    refreshSelected(initialObjectId)
      .catch((reason) => {
        if (active) setError(messageFrom(reason, "Objektdetails konnten nicht geladen werden."));
      })
      .finally(() => {
        if (active) onInitialObjectOpened();
      });
    return () => {
      active = false;
    };
  }, [initialObjectId, onInitialObjectOpened, refreshSelected]);

  async function openObject(object: SecurityObject) {
    setError("");
    try {
      await refreshSelected(object.id);
    } catch (reason) {
      setError(messageFrom(reason, "Objektdetails konnten nicht geladen werden."));
    }
  }

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const firstName = optionalValue(data, "contact_first_name");
    const lastName = optionalValue(data, "contact_last_name");
    if (Boolean(firstName) !== Boolean(lastName)) {
      setError("Für einen Ansprechpartner sind Vor- und Nachname erforderlich.");
      return;
    }

    setBusy(true);
    try {
      const created = await createObject({
        customer_id: String(data.get("customer_id")),
        name: String(data.get("name")).trim(),
        code: optionalValue(data, "code"),
        object_type: optionalValue(data, "object_type"),
        description: optionalValue(data, "description"),
        status: String(data.get("status")) as ObjectStatus,
        operating_hours: optionalValue(data, "operating_hours"),
        service_times: optionalValue(data, "service_times"),
        staffing_requirements: optionalValue(data, "staffing_requirements"),
        qualification_requirements: qualificationRequirements(data),
        address: formAddress(data, "new_object"),
        contacts: firstName && lastName
          ? [{
            first_name: firstName,
            last_name: lastName,
            role: optionalValue(data, "contact_role"),
            email: optionalValue(data, "contact_email"),
            phone: optionalValue(data, "contact_phone"),
            is_primary: data.get("contact_primary") === "on",
          }]
          : [],
      });
      form.reset();
      setOffset(0);
      await loadObjects();
      await refreshSelected(created.id);
    } catch (reason) {
      setError(messageFrom(reason, "Objekt konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    try {
      const address = data.get("remove_address") === "on"
        ? null
        : formAddress(data, "edit_object");
      const updated = await updateObject(selected.id, {
        ...(canReadCustomers && String(data.get("customer_id")) !== selected.customer_id
          ? { customer_id: String(data.get("customer_id")) }
          : {}),
        name: String(data.get("name")).trim(),
        code: String(data.get("code")).trim(),
        object_type: optionalValue(data, "object_type") ?? null,
        description: optionalValue(data, "description") ?? null,
        status: String(data.get("status")) as ObjectStatus,
        operating_hours: optionalValue(data, "operating_hours") ?? null,
        service_times: optionalValue(data, "service_times") ?? null,
        staffing_requirements: optionalValue(data, "staffing_requirements") ?? null,
        qualification_requirements: qualificationRequirements(data),
        address,
      });
      await Promise.all([loadObjects(), refreshSelected(updated.id)]);
    } catch (reason) {
      setError(messageFrom(reason, "Objektdaten konnten nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function changeArchiveState() {
    if (!selected) return;
    const action = selected.archived_at ? reactivateObject : archiveObject;
    if (!selected.archived_at && !window.confirm(`Soll „${selected.name}“ archiviert werden?`)) return;
    setBusy(true);
    try {
      await action(selected.id);
      await Promise.all([loadObjects(), refreshSelected(selected.id)]);
    } catch (reason) {
      setError(messageFrom(reason, "Archivierungsstatus konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    try {
      await createObjectContact(selected.id, {
        first_name: String(data.get("first_name")).trim(),
        last_name: String(data.get("last_name")).trim(),
        role: optionalValue(data, "contact_role"),
        email: optionalValue(data, "contact_email"),
        phone: optionalValue(data, "contact_phone"),
        is_primary: data.get("is_primary") === "on",
      });
      form.reset();
      await refreshSelected(selected.id);
    } catch (reason) {
      setError(messageFrom(reason, "Ansprechpartner konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitContactUpdate(event: FormEvent<HTMLFormElement>, contact: ObjectContact) {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await updateObjectContact(selected.id, contact.id, {
        first_name: String(data.get("first_name")).trim(),
        last_name: String(data.get("last_name")).trim(),
        role: optionalValue(data, "contact_role") ?? null,
        email: optionalValue(data, "contact_email") ?? null,
        phone: optionalValue(data, "contact_phone") ?? null,
        is_primary: data.get("is_primary") === "on",
      });
      await refreshSelected(selected.id);
    } catch (reason) {
      setError(messageFrom(reason, "Ansprechpartner konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function removeContact(contact: ObjectContact) {
    if (!selected || !window.confirm(`${contact.first_name} ${contact.last_name} entfernen?`)) return;
    setBusy(true);
    try {
      await deleteObjectContact(selected.id, contact.id);
      await refreshSelected(selected.id);
    } catch (reason) {
      setError(messageFrom(reason, "Ansprechpartner konnte nicht entfernt werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitAssignments(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    try {
      const updated = await updateObjectAssignments(selected.id, assignedUserIds);
      setAssignments(updated);
    } catch (reason) {
      setError(messageFrom(reason, "Objektzuweisungen konnten nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitSecurity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    try {
      const updated = await updateObjectSecurity(selected.id, securityForm);
      setSecurity(updated);
      await getObjectHistory(selected.id).then(setHistory);
    } catch (reason) {
      setError(messageFrom(reason, "Sicherheitsinformationen konnten nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  if (!canRead) {
    return <section className="panel"><h2>Kein Objektzugriff</h2><p className="muted">Deinem Konto fehlt die Leseberechtigung für Objekte.</p></section>;
  }

  return (
    <section className="object-module">
      <section className="intro object-intro">
        <p className="eyebrow">OBJEKTVERWALTUNG</p>
        <h1>Objekte</h1>
        <p>Kundenbezogene Standorte, Ansprechpartner und zugewiesene Teams.</p>
      </section>

      {error && <p className="alert page-alert" role="alert">{error}</p>}

      <section className="content-grid">
        <section className="panel">
          <div className="panel-heading">
            <div><p className="eyebrow">STAMMDATEN</p><h2>Objektliste</h2></div>
            <span className="result-count">{total} Einträge</span>
          </div>
          <label className="search-field">
            <span className="sr-only">Objekte suchen</span>
            <span aria-hidden="true">⌕</span>
            <input
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setOffset(0);
              }}
              placeholder="Name, Nummer, Kontakt oder Adresse suchen"
            />
          </label>
          <div className="filter-row">
            <label>Status
              <select value={statusFilter} onChange={(event) => {
                setStatusFilter(event.target.value as ObjectStatus | "");
                setOffset(0);
              }}>
                <option value="">Alle Status</option>
                {Object.entries(statusNames).map(([value, name]) =>
                  <option key={value} value={value}>{name}</option>,
                )}
              </select>
            </label>
            <label>Kunde
              <select value={customerFilter} onChange={(event) => {
                setCustomerFilter(event.target.value);
                setOffset(0);
              }}>
                <option value="">Alle Kunden</option>
                {customers.map((customer) =>
                  <option key={customer.id} value={customer.id}>{customer.company_name}</option>,
                )}
              </select>
            </label>
            <label>Sortieren nach
              <select value={sortBy} onChange={(event) => setSortBy(event.target.value as ObjectSort)}>
                <option value="name">Objektname</option>
                <option value="code">Objektnummer</option>
                <option value="created_at">Angelegt am</option>
                <option value="status">Status</option>
              </select>
            </label>
            <label>Reihenfolge
              <select value={sortOrder} onChange={(event) => setSortOrder(event.target.value as "asc" | "desc")}>
                <option value="asc">Aufsteigend</option>
                <option value="desc">Absteigend</option>
              </select>
            </label>
            {(canManage || canManageAll) && <label className="checkbox-label">
              <input type="checkbox" checked={includeArchived} onChange={(event) => {
                setIncludeArchived(event.target.checked);
                setOffset(0);
              }} />
              Archivierte einblenden
            </label>}
          </div>
          <div className="table-scroll">
            <table>
              <thead><tr><th>Objekt</th><th>Kunde</th><th>Anschrift</th><th>Status</th><th>Details</th></tr></thead>
              <tbody>
                {objects.map((object) => (
                  <tr key={object.id} className={object.archived_at ? "archived-row" : ""}>
                    <td><strong>{object.name}</strong><small>{object.code}</small></td>
                    <td>{object.customer_name}</td>
                    <td>{object.address
                      ? <>{object.address.street} {object.address.house_number}<small>{object.address.postal_code} {object.address.city}</small></>
                      : <span className="muted">Keine Anschrift</span>}</td>
                    <td><span className={`status status-${object.status}`}>
                      {object.archived_at ? "Archiviert" : statusNames[object.status]}
                    </span></td>
                    <td><button className="text-button" onClick={() => void openObject(object)}>Öffnen</button></td>
                  </tr>
                ))}
                {objects.length === 0 && <tr><td className="empty" colSpan={5}>Keine passenden Objekte vorhanden.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <span className="result-count">{total === 0 ? 0 : offset + 1}–{Math.min(offset + pageSize, total)} von {total}</span>
            <div>
              <button className="secondary-button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Zurück</button>
              <button className="secondary-button" disabled={offset + pageSize >= total} onClick={() => setOffset(offset + pageSize)}>Weiter</button>
            </div>
          </div>
        </section>

        {canCreate && canReadCustomers && <aside className="panel form-panel">
          <div className="panel-heading"><div><p className="eyebrow">NEU ANLEGEN</p><h2>Objekt hinzufügen</h2></div></div>
          <form onSubmit={submitCreate}>
            <label>Kunde <span aria-hidden="true">*</span>
              <select name="customer_id" required defaultValue="">
                <option value="" disabled>Kunde auswählen</option>
                {customers.filter((customer) => !customer.archived_at).map((customer) =>
                  <option key={customer.id} value={customer.id}>{customer.company_name} · {customer.customer_number}</option>,
                )}
              </select>
            </label>
            <label>Objektname <span aria-hidden="true">*</span><input name="name" required maxLength={200} /></label>
            <label>Objektnummer<input name="code" maxLength={50} /></label>
            <label>Objekttyp<input name="object_type" maxLength={120} /></label>
            <label>Status<select name="status" defaultValue="active">
              {Object.entries(statusNames).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
            </select></label>
            <label>Beschreibung<textarea name="description" maxLength={10000} rows={3} /></label>
            <AddressFields prefix="new_object" />
            <label>Betriebszeiten<input name="operating_hours" maxLength={200} /></label>
            <label>Leistungszeiten<input name="service_times" maxLength={200} /></label>
            <label>Personalbedarf<textarea name="staffing_requirements" maxLength={10000} rows={2} /></label>
            <label>Für Dienste erforderliche Qualifikationen (je Zeile eine)
              <textarea name="qualification_requirements" maxLength={16000} rows={3} />
            </label>
            <fieldset>
              <legend>Erster Ansprechpartner (optional)</legend>
              <div className="form-row">
                <label>Vorname<input name="contact_first_name" maxLength={100} /></label>
                <label>Nachname<input name="contact_last_name" maxLength={100} /></label>
              </div>
              <label>Funktion<input name="contact_role" maxLength={120} /></label>
              <label>E-Mail<input name="contact_email" type="email" maxLength={254} /></label>
              <label>Telefon<input name="contact_phone" type="tel" maxLength={40} /></label>
              <label className="checkbox-label"><input type="checkbox" name="contact_primary" /> Primärkontakt</label>
            </fieldset>
            <button type="submit" disabled={busy}>{busy ? "Wird gespeichert …" : "Objekt speichern"}</button>
          </form>
        </aside>}
      </section>

      {selected && <section className="panel detail-panel" aria-labelledby="object-detail-title">
        <div className="panel-heading">
          <div><p className="eyebrow">OBJEKTDETAILS · {selected.code}</p>
            <h2 id="object-detail-title">{selected.name}</h2></div>
          <button className="secondary-button" onClick={() => setSelected(null)}>Schließen</button>
        </div>
        <div className="detail-grid">
          {canManage && !selected.archived_at ? <form key={selected.id} className="form-panel detail-form" onSubmit={submitUpdate}>
            {canReadCustomers ? <label>Kunde<select name="customer_id" defaultValue={selected.customer_id} required>
              {!customers.some((customer) => customer.id === selected.customer_id)
                && <option value={selected.customer_id}>{selected.customer_name} (archiviert)</option>}
              {customers.map((customer) =>
                <option key={customer.id} value={customer.id}>{customer.company_name}</option>,
              )}
            </select></label> : <p><strong>Kunde:</strong> {selected.customer_name}</p>}
            <label>Objektname<input name="name" required maxLength={200} defaultValue={selected.name} /></label>
            <label>Objektnummer<input name="code" required maxLength={50} defaultValue={selected.code} /></label>
            <label>Objekttyp<input name="object_type" maxLength={120} defaultValue={selected.object_type ?? ""} /></label>
            <label>Status<select name="status" defaultValue={selected.status}>
              {Object.entries(statusNames).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
            </select></label>
            <label>Beschreibung<textarea name="description" maxLength={10000} rows={3} defaultValue={selected.description ?? ""} /></label>
            <AddressFields prefix="edit_object" address={selected.address} />
            {selected.address && <label className="checkbox-label">
              <input type="checkbox" name="remove_address" /> Objektanschrift entfernen
            </label>}
            <label>Betriebszeiten<input name="operating_hours" maxLength={200} defaultValue={selected.operating_hours ?? ""} /></label>
            <label>Leistungszeiten<input name="service_times" maxLength={200} defaultValue={selected.service_times ?? ""} /></label>
            <label>Personalbedarf<textarea name="staffing_requirements" maxLength={10000} rows={2} defaultValue={selected.staffing_requirements ?? ""} /></label>
            <label>Für Dienste erforderliche Qualifikationen (je Zeile eine)
              <textarea name="qualification_requirements" maxLength={16000} rows={3}
                defaultValue={selected.qualification_requirements?.join("\n") ?? ""} />
            </label>
            <button type="submit" disabled={busy}>Änderungen speichern</button>
          </form> : <div className="detail-summary">
            <p><strong>Kunde:</strong> {selected.customer_name}</p>
            <p><strong>Status:</strong> {selected.archived_at ? "Archiviert" : statusNames[selected.status]}</p>
            {selected.object_type && <p><strong>Objekttyp:</strong> {selected.object_type}</p>}
            {selected.description && <p><strong>Beschreibung:</strong><br />{selected.description}</p>}
            <p><strong>Für Dienste erforderliche Qualifikationen:</strong><br />
              {selected.qualification_requirements?.length
                ? selected.qualification_requirements.join(", ")
                : "Keine Anforderungen hinterlegt"}
            </p>
            {selected.address && <p><strong>Objektanschrift:</strong><br />
              {selected.address.street} {selected.address.house_number}<br />
              {selected.address.postal_code} {selected.address.city}<br />{selected.address.country_code}</p>}
          </div>}
          <div className="detail-side">
            {canManage && <div className="archive-box">
              <h3>{selected.archived_at ? "Archiviertes Objekt" : "Objektstatus"}</h3>
              <p className="muted">{selected.archived_at
                ? `Archiviert am ${new Date(selected.archived_at).toLocaleString("de-DE")}.`
                : "Archivierte Objekte werden standardmäßig aus der Liste ausgeblendet."}</p>
              <button className={selected.archived_at ? "primary-button" : "danger-button"}
                disabled={busy} onClick={() => void changeArchiveState()}>
                {selected.archived_at ? "Reaktivieren" : "Objekt archivieren"}
              </button>
            </div>}

            <section className="contact-section">
              <h3>Ansprechpartner</h3>
              {selected.contacts.length === 0 && <p className="muted">Noch keine Ansprechpartner hinterlegt.</p>}
              {selected.contacts.map((contact) => (
                <article className="contact-card" key={contact.id}>
                  {canManage && !selected.archived_at ? <form className="contact-form"
                    onSubmit={(event) => void submitContactUpdate(event, contact)}>
                    <div className="form-row">
                      <label>Vorname<input name="first_name" required maxLength={100} defaultValue={contact.first_name} /></label>
                      <label>Nachname<input name="last_name" required maxLength={100} defaultValue={contact.last_name} /></label>
                    </div>
                    <label>Funktion<input name="contact_role" maxLength={120} defaultValue={contact.role ?? ""} /></label>
                    <label>E-Mail<input name="contact_email" type="email" maxLength={254} defaultValue={contact.email ?? ""} /></label>
                    <label>Telefon<input name="contact_phone" type="tel" maxLength={40} defaultValue={contact.phone ?? ""} /></label>
                    <label className="checkbox-label"><input type="checkbox" name="is_primary" defaultChecked={contact.is_primary} /> Primärkontakt</label>
                    <div className="contact-actions">
                      <button className="secondary-button" type="submit" disabled={busy}>Speichern</button>
                      <button type="button" className="text-button danger-text" disabled={busy}
                        onClick={() => void removeContact(contact)}>Entfernen</button>
                    </div>
                  </form> : <div>
                    <strong>{contact.first_name} {contact.last_name}</strong>
                    {contact.is_primary && <span className="primary-tag">Primär</span>}
                    {contact.role && <small>{contact.role}</small>}
                    {contact.email && <small><a href={`mailto:${contact.email}`}>{contact.email}</a></small>}
                    {contact.phone && <small>{contact.phone}</small>}
                  </div>}
                </article>
              ))}
              {canManage && !selected.archived_at && <form className="contact-form" onSubmit={submitContact}>
                <h4>Ansprechpartner hinzufügen</h4>
                <div className="form-row">
                  <label>Vorname<input name="first_name" required maxLength={100} /></label>
                  <label>Nachname<input name="last_name" required maxLength={100} /></label>
                </div>
                <label>Funktion<input name="contact_role" maxLength={120} /></label>
                <label>E-Mail<input name="contact_email" type="email" maxLength={254} /></label>
                <label>Telefon<input name="contact_phone" type="tel" maxLength={40} /></label>
                <label className="checkbox-label"><input type="checkbox" name="is_primary" /> Primärkontakt</label>
                <button className="secondary-button" type="submit" disabled={busy}>Hinzufügen</button>
              </form>}
            </section>

            {canAssign && <section className="assignment-section">
              <h3>Objektzuweisungen</h3>
              <p className="muted">Nur zugewiesene Benutzer mit Leserecht können dieses Objekt öffnen.</p>
              <form className="contact-form" onSubmit={submitAssignments}>
                <label>Aktive Mitarbeiter und Objektleitungen
                  <select multiple size={5} value={assignedUserIds}
                    onChange={(event) => setAssignedUserIds(
                      Array.from(event.target.selectedOptions, (option) => option.value),
                    )}>
                    {assignmentCandidates.map((candidate) =>
                      <option key={candidate.id} value={candidate.id}>
                        {candidate.full_name} · {candidate.username}
                      </option>,
                    )}
                  </select>
                </label>
                <button className="secondary-button" type="submit" disabled={busy}>Zuweisungen speichern</button>
              </form>
              <ul className="assignment-list">
                {assignments.map((assignment) =>
                  <li key={assignment.user_id}>{assignment.full_name}<small>{assignment.username}</small></li>,
                )}
              </ul>
            </section>}

            {canReadSensitive && <section className="security-section">
              <h3>Sicherheits- und Zutrittsdaten</h3>
              {canManageSensitive && !selected.archived_at ? <form className="contact-form" onSubmit={submitSecurity}>
                <label>Sicherheitsanforderungen<textarea maxLength={10000} rows={3}
                  value={securityForm.security_requirements}
                  onChange={(event) => setSecurityForm({ ...securityForm, security_requirements: event.target.value })} /></label>
                <label>Zutrittsinformationen<textarea maxLength={10000} rows={3}
                  value={securityForm.access_information}
                  onChange={(event) => setSecurityForm({ ...securityForm, access_information: event.target.value })} /></label>
                <label>Notfallkontakt<input maxLength={200} value={securityForm.emergency_contact}
                  onChange={(event) => setSecurityForm({ ...securityForm, emergency_contact: event.target.value })} /></label>
                <button className="secondary-button" type="submit" disabled={busy}>Sicherheitsdaten speichern</button>
              </form> : <div className="detail-summary sensitive-summary">
                <p><strong>Sicherheitsanforderungen:</strong><br />{security?.security_requirements || "Keine Angaben"}</p>
                <p><strong>Zutrittsinformationen:</strong><br />{security?.access_information || "Keine Angaben"}</p>
                <p><strong>Notfallkontakt:</strong><br />{security?.emergency_contact || "Keine Angaben"}</p>
              </div>}
            </section>}
          </div>
        </div>
        <section className="history-section">
          <h3>Änderungshistorie</h3>
          {history.length === 0 ? <p className="muted">Noch keine Historieneinträge.</p> : (
            <ol className="history-list">
              {history.map((item) => <li key={item.id}>
                <strong>{actionNames[item.action] ?? item.action}</strong>
                <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString("de-DE")}</time>
                {item.changed_fields.length > 0 && <small>Geänderte Bereiche: {item.changed_fields.join(", ")}</small>}
              </li>)}
            </ol>
          )}
        </section>
      </section>}
    </section>
  );
}
