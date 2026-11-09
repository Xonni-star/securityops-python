import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  acknowledgeDocumentRead,
  archiveContract,
  archiveDocument,
  ContractInput,
  createContract,
  createDocument,
  decideDocumentApproval,
  downloadDocumentVersion,
  generateReminders,
  getContract,
  getContracts,
  getCustomers,
  getDocument,
  getDocumentApprovals,
  getDocuments,
  getEmployees,
  getObjects,
  getReminderSettings,
  getReminders,
  restoreContract,
  restoreDocument,
  requestDocumentApproval,
  updateContract,
  updateDocument,
  updateReminder,
  updateReminderSettings,
  uploadDocumentVersion,
} from "./api";
import type {
  AuthUser,
  ContractType,
  Customer,
  Employee,
  GlobalSearchResult,
  ManagedContract,
  ManagedDocument,
  ManagedReminder,
  ObjectPage,
  ReminderSettings,
} from "./types";

type ModuleTab = "documents" | "approvals" | "contracts" | "reminders";

const contractTypes: Record<ContractType, string> = {
  customer: "Kundenvertrag",
  object: "Objektvertrag",
  personnel: "Personalvertrag",
  service: "Dienstleistungsvertrag",
  additional: "Zusatzvertrag",
  other: "Sonstiger Vertrag",
};

const documentStatuses = {
  draft: "Entwurf",
  active: "Aktiv",
  expired: "Abgelaufen",
  archived: "Archiviert",
} as const;

const contractStatuses = {
  draft: "Entwurf",
  active: "Aktiv",
  terminated: "Gekündigt",
  expired: "Ausgelaufen",
  archived: "Archiviert",
} as const;

const reminderNames = {
  document_expiry: "Dokumentenablauf",
  contract_expiry: "Vertragsablauf",
  contract_termination: "Kündigungsfrist",
  contract_renewal: "Verlängerung",
} as const;

function messageFrom(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function optionalString(value: FormDataEntryValue | null) {
  return String(value ?? "").trim() || null;
}

function dateLabel(value: string | null | undefined) {
  return value ? new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString("de-DE") : "—";
}

function dateTimeLabel(value: string) {
  return new Date(value).toLocaleString("de-DE");
}

export default function DocumentContractManagement({
  user,
  initialSearchResult = null,
}: {
  user: AuthUser;
  initialSearchResult?: Pick<GlobalSearchResult, "id" | "type"> | null;
}) {
  const canReadDocuments = user.permissions.includes("documents.read");
  const canCreateDocuments = user.permissions.includes("documents.create");
  const canUpdateDocuments = user.permissions.includes("documents.update");
  const canArchiveDocuments = user.permissions.includes("documents.archive");
  const canDownloadDocuments = user.permissions.includes("documents.download");
  const canApproveDocuments = user.permissions.includes("documents.approve");
  const canReadContracts = user.permissions.includes("contracts.read");
  const canCreateContracts = user.permissions.includes("contracts.create");
  const canUpdateContracts = user.permissions.includes("contracts.update");
  const canArchiveContracts = user.permissions.includes("contracts.archive");
  const canManageReminders = user.permissions.includes("contracts.manage_reminders");
  const canReadCustomers = user.permissions.includes("customers.read");
  const canReadObjects = user.permissions.includes("objects.read");
  const canReadEmployees = user.permissions.includes("employees.read");

  const [tab, setTab] = useState<ModuleTab>(
    canReadDocuments || canCreateDocuments ? "documents" : "contracts",
  );
  const [documents, setDocuments] = useState<ManagedDocument[]>([]);
  const [contracts, setContracts] = useState<ManagedContract[]>([]);
  const [approvals, setApprovals] = useState<Awaited<ReturnType<typeof getDocumentApprovals>>>([]);
  const [reminders, setReminders] = useState<ManagedReminder[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [objects, setObjects] = useState<ObjectPage["items"]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<ManagedDocument | null>(null);
  const [selectedContract, setSelectedContract] = useState<ManagedContract | null>(null);
  const [reminderSettings, setReminderSettings] = useState<ReminderSettings | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [contractTypeFilter, setContractTypeFilter] = useState<ContractType | "">("");
  const [newContractType, setNewContractType] = useState<ContractType>("customer");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const categories = useMemo(
    () => [...new Set(documents.map((item) => item.category))].sort((a, b) => a.localeCompare(b, "de")),
    [documents],
  );

  const loadDocuments = useCallback(async () => {
    if (!canReadDocuments) return;
    const page = await getDocuments({
      q: query,
      status: statusFilter,
      category: categoryFilter,
      includeArchived,
    });
    setDocuments(page.items);
  }, [canReadDocuments, categoryFilter, includeArchived, query, statusFilter]);

  const loadContracts = useCallback(async () => {
    if (!canReadContracts) return;
    const page = await getContracts({
      q: query,
      status: statusFilter,
      contractType: contractTypeFilter,
      includeArchived,
    });
    setContracts(page.items);
  }, [canReadContracts, contractTypeFilter, includeArchived, query, statusFilter]);

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (tab === "documents") await loadDocuments();
      if (tab === "approvals") {
        setApprovals(canReadDocuments ? await getDocumentApprovals() : []);
      }
      if (tab === "contracts") await loadContracts();
      if (tab === "reminders") {
        const [items, settings] = await Promise.all([
          canReadContracts ? getReminders() : Promise.resolve([]),
          canManageReminders ? getReminderSettings() : Promise.resolve(null),
        ]);
        setReminders(items);
        setReminderSettings(settings);
      }
    } catch (reason) {
      setError(messageFrom(reason, "Die Daten konnten nicht geladen werden."));
    } finally {
      setLoading(false);
    }
  }, [canManageReminders, canReadContracts, canReadDocuments, loadContracts, loadDocuments, tab]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    let active = true;
    const requests = [
      canReadDocuments
        ? getDocuments({ q: "", status: "", category: "", includeArchived: false })
          .then((page) => active && setDocuments(page.items))
        : Promise.resolve(),
      canReadCustomers
        ? getCustomers({
          q: "",
          status: "",
          contractStatus: "",
          includeArchived: false,
          sortBy: "company_name",
          sortOrder: "asc",
          limit: 100,
          offset: 0,
        }).then((page) => active && setCustomers(page.items))
        : Promise.resolve(),
      canReadObjects
        ? getObjects({
          q: "",
          status: "",
          customerId: "",
          includeArchived: false,
          sortBy: "name",
          sortOrder: "asc",
          limit: 100,
          offset: 0,
        }).then((page) => active && setObjects(page.items))
        : Promise.resolve(),
      canReadEmployees
        ? getEmployees({
          q: "",
          status: "",
          includeArchived: false,
          sortBy: "full_name",
          sortOrder: "asc",
          limit: 100,
          offset: 0,
        }).then((page) => active && setEmployees(page.items))
        : Promise.resolve(),
    ];
    void Promise.all(requests).catch((reason: unknown) => {
      if (active) setError(messageFrom(reason, "Zuordnungen konnten nicht geladen werden."));
    });
    return () => { active = false; };
  }, [canReadCustomers, canReadDocuments, canReadEmployees, canReadObjects]);

  const openDocument = useCallback(async (documentId: string) => {
    setError("");
    try {
      setSelectedDocument(await getDocument(documentId));
    } catch (reason) {
      setError(messageFrom(reason, "Dokumentdetails konnten nicht geladen werden."));
    }
  }, []);

  const openContract = useCallback(async (contractId: string) => {
    setError("");
    try {
      setSelectedContract(await getContract(contractId));
    } catch (reason) {
      setError(messageFrom(reason, "Vertragsdetails konnten nicht geladen werden."));
    }
  }, []);

  useEffect(() => {
    if (initialSearchResult?.type === "document") {
      setTab("documents");
      void openDocument(initialSearchResult.id);
    } else if (initialSearchResult?.type === "contract") {
      setTab("contracts");
      void openContract(initialSearchResult.id);
    }
  }, [initialSearchResult, openContract, openDocument]);

  async function submitDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    try {
      const created = await createDocument(data);
      form.reset();
      setNotice("Das Dokument wurde sicher gespeichert.");
      await reload();
      await openDocument(created.id);
    } catch (reason) {
      setError(messageFrom(reason, "Das Dokument konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function saveDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDocument) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      const updated = await updateDocument(selectedDocument.id, {
        title: String(data.get("title")),
        category: String(data.get("category")),
        description: optionalString(data.get("description")),
        status: String(data.get("status")) as ManagedDocument["status"],
        expires_on: optionalString(data.get("expires_on")),
      });
      setSelectedDocument(updated);
      setNotice("Dokumentdaten wurden gespeichert.");
      await reload();
    } catch (reason) {
      setError(messageFrom(reason, "Dokumentdaten konnten nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitVersion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDocument) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    try {
      await uploadDocumentVersion(selectedDocument.id, data);
      form.reset();
      await openDocument(selectedDocument.id);
      setNotice("Eine neue, unveränderliche Dokumentversion wurde angelegt.");
    } catch (reason) {
      setError(messageFrom(reason, "Die neue Version konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function downloadVersion(documentId: string, versionId: string, name: string) {
    setError("");
    try {
      const blob = await downloadDocumentVersion(documentId, versionId);
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = name;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(messageFrom(reason, "Die Datei konnte nicht heruntergeladen werden."));
    }
  }

  async function markAsRead(versionId: string) {
    if (!selectedDocument) return;
    setBusy(true);
    try {
      await acknowledgeDocumentRead(versionId);
      await openDocument(selectedDocument.id);
      setNotice("Lesebestätigung wurde nachvollziehbar gespeichert.");
    } catch (reason) {
      setError(messageFrom(reason, "Die Lesebestätigung konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function approve(approvalId: string, status: "approved" | "rejected") {
    setBusy(true);
    try {
      await decideDocumentApproval(approvalId, status);
      await reload();
      if (selectedDocument) await openDocument(selectedDocument.id);
      setNotice(status === "approved" ? "Version wurde freigegeben." : "Freigabe wurde abgelehnt.");
    } catch (reason) {
      setError(messageFrom(reason, "Die Freigabe konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitContract(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const input: ContractInput = {
      contract_number: String(data.get("contract_number")).trim(),
      name: String(data.get("name")).trim(),
      contract_type: String(data.get("contract_type")) as ContractType,
      counterparty: String(data.get("counterparty")).trim(),
      customer_id: String(data.get("customer_id")),
      object_id: optionalString(data.get("object_id")),
      employee_id: optionalString(data.get("employee_id")),
      starts_on: String(data.get("starts_on")),
      ends_on: optionalString(data.get("ends_on")),
      notice_period_days: optionalString(data.get("notice_period_days"))
        ? Number(data.get("notice_period_days"))
        : null,
      renewal_rule: optionalString(data.get("renewal_rule")),
      status: String(data.get("status")) as ContractInput["status"],
      document_id: optionalString(data.get("document_id")),
      internal_notes: optionalString(data.get("internal_notes")),
    };
    setBusy(true);
    setError("");
    try {
      const created = await createContract(input);
      form.reset();
      setNotice("Der Vertrag wurde angelegt und protokolliert.");
      await reload();
      await openContract(created.id);
    } catch (reason) {
      setError(messageFrom(reason, "Der Vertrag konnte nicht angelegt werden."));
    } finally {
      setBusy(false);
    }
  }

  async function saveContract(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedContract) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      const updated = await updateContract(selectedContract.id, {
        name: String(data.get("name")).trim(),
        contract_number: String(data.get("contract_number")).trim(),
        contract_type: String(data.get("contract_type")) as ContractType,
        counterparty: String(data.get("counterparty")).trim(),
        status: String(data.get("status")) as ContractInput["status"],
        starts_on: String(data.get("starts_on")),
        ends_on: optionalString(data.get("ends_on")),
        notice_period_days: optionalString(data.get("notice_period_days"))
          ? Number(data.get("notice_period_days"))
          : null,
        renewal_rule: optionalString(data.get("renewal_rule")),
        internal_notes: optionalString(data.get("internal_notes")),
      });
      setSelectedContract(updated);
      await reload();
      setNotice("Vertrag wurde gespeichert.");
    } catch (reason) {
      setError(messageFrom(reason, "Der Vertrag konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function archiveSelectedDocument() {
    if (!selectedDocument) return;
    setBusy(true);
    try {
      const item = selectedDocument.archived_at
        ? await restoreDocument(selectedDocument.id)
        : await archiveDocument(selectedDocument.id);
      setSelectedDocument(item);
      await reload();
      setNotice(item.archived_at ? "Dokument wurde archiviert." : "Dokument wurde wiederhergestellt.");
    } catch (reason) {
      setError(messageFrom(reason, "Der Archivstatus konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function archiveSelectedContract() {
    if (!selectedContract) return;
    setBusy(true);
    try {
      const item = selectedContract.archived_at
        ? await restoreContract(selectedContract.id)
        : await archiveContract(selectedContract.id);
      setSelectedContract(item);
      await reload();
      setNotice(item.archived_at ? "Vertrag wurde archiviert." : "Vertrag wurde wiederhergestellt.");
    } catch (reason) {
      setError(messageFrom(reason, "Der Archivstatus konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function refreshReminders() {
    setBusy(true);
    setError("");
    try {
      const result = await generateReminders();
      setNotice(`${result.created} neue Erinnerung(en) wurden geplant.`);
      await reload();
    } catch (reason) {
      setError(messageFrom(reason, "Erinnerungen konnten nicht aktualisiert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function saveReminderSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const leadDays = String(data.get("lead_days"))
      .split(",")
      .map((value) => Number(value.trim()))
      .filter((value) => Number.isInteger(value) && value >= 0);
    setBusy(true);
    setError("");
    try {
      const updated = await updateReminderSettings(leadDays);
      setReminderSettings(updated);
      setNotice("Vorlaufzeiten wurden gespeichert.");
      await refreshReminders();
    } catch (reason) {
      setError(messageFrom(reason, "Vorlaufzeiten konnten nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function markReminder(reminder: ManagedReminder, status: "completed" | "dismissed") {
    setBusy(true);
    try {
      await updateReminder(reminder.id, status);
      await reload();
    } catch (reason) {
      setError(messageFrom(reason, "Die Erinnerung konnte nicht aktualisiert werden."));
    } finally {
      setBusy(false);
    }
  }

  const visibleTabs: Array<{ id: ModuleTab; title: string; visible: boolean }> = [
    { id: "documents", title: "Dokumente", visible: canReadDocuments || canCreateDocuments },
    { id: "approvals", title: "Freigaben", visible: canReadDocuments },
    { id: "contracts", title: "Verträge", visible: canReadContracts || canCreateContracts },
    { id: "reminders", title: "Erinnerungen", visible: canReadContracts },
  ];

  return (
    <section className="document-module">
      <header className="document-intro">
        <div>
          <p className="eyebrow">VERWALTUNG</p>
          <h1>Dokumente und Verträge</h1>
          <p>Geschützte Ablage, nachvollziehbare Versionen und Vertragsfristen.</p>
        </div>
      </header>
      <nav className="module-tabs" aria-label="Dokumenten- und Vertragsverwaltung">
        {visibleTabs.map((item) => (
          <button
            key={item.id}
            className={tab === item.id ? "module-tab active" : "module-tab"}
            onClick={() => {
              setTab(item.id);
              setSelectedDocument(null);
              setSelectedContract(null);
              setNotice("");
              setError("");
            }}
          >
            {item.title}
          </button>
        ))}
      </nav>
      {error && <p className="alert page-alert" role="alert">{error}</p>}
      {notice && <p className="success-message" role="status">{notice}</p>}

      {tab === "documents" && (
        <>
          {canReadDocuments && <section className="panel document-list-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">GESCHÜTZTER SPEICHER</p><h2>Dokumentenarchiv</h2></div>
              <span className="result-count">{documents.length} Einträge</span>
            </div>
            <div className="document-filter-row">
              <label className="search-field">
                <span aria-hidden="true">⌕</span>
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Nummer, Name oder Beschreibung suchen" />
              </label>
              <label>Status
                <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="">Alle Status</option>
                  {Object.entries(documentStatuses).map(([key, label]) =>
                    <option key={key} value={key}>{label}</option>,
                  )}
                </select>
              </label>
              <label>Kategorie
                <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
                  <option value="">Alle Kategorien</option>
                  {categories.map((category) => <option key={category}>{category}</option>)}
                </select>
              </label>
              {canArchiveDocuments && <label className="checkbox-label">
                <input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} />
                Archivierte anzeigen
              </label>}
              <button className="secondary-button" onClick={() => void reload()} disabled={loading}>Suchen</button>
            </div>
            {loading ? <p className="muted" role="status">Dokumente werden geladen …</p> : (
              <div className="table-scroll">
                <table>
                  <thead><tr><th>Dokument</th><th>Kategorie</th><th>Status</th><th>Ablaufdatum</th><th>Version</th><th></th></tr></thead>
                  <tbody>
                    {documents.map((item) => (
                      <tr key={item.id} className={item.archived_at ? "archived-row" : ""}>
                        <td><strong>{item.title}</strong><small>{item.document_number}</small></td>
                        <td>{item.category}</td>
                        <td><span className="status">{documentStatuses[item.status]}</span></td>
                        <td>{dateLabel(item.expires_on)}</td>
                        <td>{item.latest_version ? `v${item.latest_version.version}` : "—"}</td>
                        <td><button className="text-button" onClick={() => void openDocument(item.id)}>Öffnen</button></td>
                      </tr>
                    ))}
                    {!documents.length && <tr><td className="empty" colSpan={6}>Keine passenden Dokumente vorhanden.</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
          </section>}
          {canCreateDocuments && <section className="panel document-create-panel form-panel">
            <div className="panel-heading"><div><p className="eyebrow">NEU ANLEGEN</p><h2>Dokument sicher hochladen</h2></div></div>
            <p className="muted">Erlaubt: PDF, PNG, JPG/JPEG, DOCX und XLSX. Die Datei wird privat abgelegt und serverseitig geprüft.</p>
            <form onSubmit={(event) => void submitDocument(event)}>
              <div className="form-row">
                <label>Dokumentnummer<input name="document_number" required maxLength={80} /></label>
                <label>Titel<input name="title" required maxLength={200} /></label>
              </div>
              <div className="form-row">
                <label>Kategorie<input name="category" required maxLength={80} placeholder="z. B. Versicherung" /></label>
                <label>Status<select name="status" defaultValue="active"><option value="active">Aktiv</option><option value="draft">Entwurf</option></select></label>
              </div>
              <label>Beschreibung<textarea name="description" rows={2} maxLength={10000} /></label>
              <div className="form-row">
                <label>Ablaufdatum<input type="date" name="expires_on" /></label>
                <label>Datei<input type="file" name="file" required accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx,application/pdf,image/png,image/jpeg,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" /></label>
              </div>
              <AssignmentFields customers={customers} objects={objects} employees={employees} />
              <button type="submit" disabled={busy}>{busy ? "Wird sicher gespeichert …" : "Dokument speichern"}</button>
            </form>
          </section>}
          {selectedDocument && <section className="panel detail-panel" aria-labelledby="document-detail-title">
            <div className="panel-heading">
              <div><p className="eyebrow">DOKUMENT · {selectedDocument.document_number}</p><h2 id="document-detail-title">{selectedDocument.title}</h2></div>
              <button className="secondary-button" onClick={() => setSelectedDocument(null)}>Schließen</button>
            </div>
            <p className="muted">Angelegt {dateTimeLabel(selectedDocument.created_at)} · Geändert {dateTimeLabel(selectedDocument.updated_at)}</p>
            <div className="document-detail-grid">
              {canUpdateDocuments && !selectedDocument.archived_at ? <form className="form-panel detail-form" onSubmit={(event) => void saveDocument(event)}>
                <label>Titel<input name="title" required maxLength={200} defaultValue={selectedDocument.title} /></label>
                <label>Kategorie<input name="category" required maxLength={80} defaultValue={selectedDocument.category} /></label>
                <label>Status<select name="status" defaultValue={selectedDocument.status}>
                  {(["draft", "active", "expired"] as const).map((value) => <option key={value} value={value}>{documentStatuses[value]}</option>)}
                </select></label>
                <label>Ablaufdatum<input type="date" name="expires_on" defaultValue={selectedDocument.expires_on ?? ""} /></label>
                <label>Beschreibung<textarea name="description" rows={3} maxLength={10000} defaultValue={selectedDocument.description ?? ""} /></label>
                <button type="submit" disabled={busy}>Änderungen speichern</button>
              </form> : <div className="detail-summary">
                <p><strong>Status:</strong> {documentStatuses[selectedDocument.status]}</p>
                <p><strong>Kategorie:</strong> {selectedDocument.category}</p>
                <p><strong>Ablaufdatum:</strong> {dateLabel(selectedDocument.expires_on)}</p>
                {selectedDocument.description && <p><strong>Beschreibung:</strong><br />{selectedDocument.description}</p>}
              </div>}
              <div className="detail-side">
                {canArchiveDocuments && <div className="archive-box">
                  <h3>{selectedDocument.archived_at ? "Archiviertes Dokument" : "Dokument archivieren"}</h3>
                  <p className="muted">Archivierung behält alle Versionen und Protokolle; Dateien werden nicht endgültig gelöscht.</p>
                  <button className={selectedDocument.archived_at ? "primary-button" : "danger-button"} disabled={busy}
                    onClick={() => void archiveSelectedDocument()}>
                    {selectedDocument.archived_at ? "Wiederherstellen" : "Archivieren"}
                  </button>
                </div>}
                <div className="version-section">
                  <h3>Versionen</h3>
                  {!selectedDocument.versions?.length && <p className="muted">Noch keine Version vorhanden.</p>}
                  {selectedDocument.versions?.map((version) => {
                    const receipt = selectedDocument.read_receipts?.some((item) =>
                      item.version_id === version.id && item.user_id === user.id,
                    );
                    return <article className="version-card" key={version.id}>
                      <div><strong>Version {version.version} · {version.file_name}</strong>
                        <small>{dateTimeLabel(version.created_at)} · {(version.size_bytes / 1024).toFixed(0)} KB · SHA-256 {version.sha256.slice(0, 12)}…</small>
                      </div>
                      <div className="version-actions">
                        {canDownloadDocuments && <button className="text-button" onClick={() => void downloadVersion(selectedDocument.id, version.id, version.file_name)}>Herunterladen</button>}
                        {!receipt && <button className="text-button" disabled={busy} onClick={() => void markAsRead(version.id)}>Gelesen bestätigen</button>}
                        {receipt && <span className="primary-tag">Gelesen</span>}
                        {canUpdateDocuments && !selectedDocument.archived_at && <button className="text-button" disabled={busy}
                          onClick={() => void requestDocumentApproval(version.id).then(() => openDocument(selectedDocument.id)).catch((reason) => setError(messageFrom(reason, "Freigabe konnte nicht angefordert werden.")))}>
                          Freigabe anfordern
                        </button>}
                      </div>
                    </article>;
                  })}
                  {canUpdateDocuments && !selectedDocument.archived_at && <form className="document-version-form" onSubmit={(event) => void submitVersion(event)}>
                    <label>Neue Version hochladen<input type="file" name="file" required accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx" /></label>
                    <button className="secondary-button" type="submit" disabled={busy}>Version hinzufügen</button>
                  </form>}
                </div>
              </div>
            </div>
            {selectedDocument.approvals?.length ? <section className="history-section">
              <h3>Freigaben und Lesebestätigungen</h3>
              <ul className="approval-list">{selectedDocument.approvals.map((approval) => (
                <li key={approval.id}>
                  <span><strong>Version {selectedDocument.versions?.find((item) => item.id === approval.version_id)?.version}</strong>
                    <small>{approval.status === "pending" ? "Offen" : approval.status === "approved" ? "Freigegeben" : "Abgelehnt"} · {dateTimeLabel(approval.created_at)}</small>
                  </span>
                  {canApproveDocuments && approval.status === "pending" && <span className="version-actions">
                    <button className="text-button" disabled={busy} onClick={() => void approve(approval.id, "approved")}>Freigeben</button>
                    <button className="text-button danger-text" disabled={busy} onClick={() => void approve(approval.id, "rejected")}>Ablehnen</button>
                  </span>}
                  {approval.decision_note && <small>{approval.decision_note}</small>}
                </li>
              ))}</ul>
              {selectedDocument.read_receipts?.map((receipt) => <p className="muted" key={receipt.id}>
                Version {selectedDocument.versions?.find((item) => item.id === receipt.version_id)?.version} bestätigt von {receipt.user_id === user.id ? "dir" : receipt.user_id} am {dateTimeLabel(receipt.read_at)}.
              </p>)}
            </section> : <section className="history-section"><h3>Freigaben und Lesebestätigungen</h3><p className="muted">Noch keine Freigabe angefordert.</p></section>}
            <section className="history-section">
              <h3>Änderungshistorie</h3>
              {!selectedDocument.history?.length ? <p className="muted">Noch keine Änderungen protokolliert.</p> : (
                <ol className="history-list">{selectedDocument.history.map((item) => (
                  <li key={item.id}><strong>{documentActionName(item.action)}</strong><time>{dateTimeLabel(item.created_at)}</time>
                    {!!item.changed_fields.length && <small>Geänderte Bereiche: {item.changed_fields.join(", ")}</small>}</li>
                ))}</ol>
              )}
            </section>
          </section>}
        </>
      )}

      {tab === "approvals" && <section className="panel">
        <div className="panel-heading"><div><p className="eyebrow">PRÜFUNG</p><h2>Offene Freigaben</h2></div>
          <button className="secondary-button" disabled={loading} onClick={() => void reload()}>Aktualisieren</button>
        </div>
        {loading ? <p className="muted">Freigaben werden geladen …</p> : approvals.length ? (
          <div className="table-scroll"><table><thead><tr><th>Dokument</th><th>Version</th><th>Angefordert</th><th>Aktion</th></tr></thead>
            <tbody>{approvals.map((approval) => <tr key={approval.id}>
              <td><button className="text-button" onClick={() => void openDocument(approval.document_id)}>{approval.document_title}<small>{approval.document_number}</small></button></td>
              <td>v{approval.version}</td><td>{dateTimeLabel(approval.created_at)}</td>
              <td>{canApproveDocuments ? <div className="version-actions">
                <button className="text-button" disabled={busy} onClick={() => void approve(approval.id, "approved")}>Freigeben</button>
                <button className="text-button danger-text" disabled={busy} onClick={() => void approve(approval.id, "rejected")}>Ablehnen</button>
              </div> : <span className="muted">Freigabe ausstehend</span>}</td>
            </tr>)}</tbody></table>
          </div>
        ) : <p className="muted">Keine offenen Freigaben.</p>}
      </section>}

      {tab === "contracts" && <>
        {canReadContracts && <section className="panel">
          <div className="panel-heading"><div><p className="eyebrow">LAUFZEITEN</p><h2>Vertragsübersicht</h2></div>
            <span className="result-count">{contracts.length} Einträge</span></div>
          <div className="document-filter-row">
            <label className="search-field"><span aria-hidden="true">⌕</span>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Nummer, Vertrag oder Partner suchen" /></label>
            <label>Status<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="">Alle Status</option>{Object.entries(contractStatuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select></label>
            <label>Vertragstyp<select value={contractTypeFilter} onChange={(event) => setContractTypeFilter(event.target.value as ContractType | "")}>
              <option value="">Alle Typen</option>{Object.entries(contractTypes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select></label>
            {canArchiveContracts && <label className="checkbox-label">
              <input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} /> Archivierte anzeigen
            </label>}
            <button className="secondary-button" disabled={loading} onClick={() => void reload()}>Suchen</button>
          </div>
          {loading ? <p className="muted">Verträge werden geladen …</p> : (
            <div className="table-scroll"><table><thead><tr><th>Vertrag</th><th>Typ / Partner</th><th>Status</th><th>Laufzeit</th><th>Kündigungsfrist</th><th></th></tr></thead>
              <tbody>{contracts.map((item) => <tr key={item.id} className={item.archived_at ? "archived-row" : ""}>
                <td><strong>{item.name}</strong><small>{item.contract_number}</small></td>
                <td>{contractTypes[item.contract_type]}<small>{item.counterparty}</small></td>
                <td><span className="status">{contractStatuses[item.status]}</span></td>
                <td>{dateLabel(item.starts_on)} – {dateLabel(item.ends_on)}</td>
                <td>{item.notice_period_days === null ? "—" : `${item.notice_period_days} Tage`}</td>
                <td><button className="text-button" onClick={() => void openContract(item.id)}>Öffnen</button></td>
              </tr>)}
              {!contracts.length && <tr><td className="empty" colSpan={6}>Keine passenden Verträge vorhanden.</td></tr>}</tbody>
            </table></div>
          )}
        </section>}
        {canCreateContracts && <section className="panel form-panel document-create-panel">
          <div className="panel-heading"><div><p className="eyebrow">NEU ANLEGEN</p><h2>Vertrag erfassen</h2></div></div>
          <form onSubmit={(event) => void submitContract(event)}>
            <div className="form-row">
              <label>Vertragsnummer<input name="contract_number" required maxLength={80} /></label>
              <label>Name<input name="name" required maxLength={200} /></label>
            </div>
            <div className="form-row">
              <label>Vertragstyp<select name="contract_type" value={newContractType}
                onChange={(event) => setNewContractType(event.target.value as ContractType)}>
                {Object.entries(contractTypes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </select></label>
              <label>Vertragspartner<input name="counterparty" required maxLength={200} /></label>
            </div>
            {canReadCustomers
              ? <label>Kunde<select name="customer_id" required defaultValue="">
                <option value="" disabled>Kunde auswählen</option>
                {customers.map((item) => <option key={item.id} value={item.id}>{item.customer_number} · {item.company_name}</option>)}
              </select></label>
              : <label>Kunden-ID<input name="customer_id" required maxLength={36} placeholder="UUID des Kunden" /></label>}
            <AssignmentFields customers={customers} objects={objects} employees={employees} contractType={newContractType} />
            <div className="form-row">
              <label>Beginn<input name="starts_on" type="date" required /></label>
              <label>Ende<input name="ends_on" type="date" /></label>
            </div>
            <div className="form-row">
              <label>Kündigungsfrist (Tage)<input name="notice_period_days" type="number" min="0" max="3650" /></label>
              <label>Status<select name="status" defaultValue="draft"><option value="draft">Entwurf</option><option value="active">Aktiv</option></select></label>
            </div>
            <label>Verlängerungsregel<textarea name="renewal_rule" rows={2} maxLength={500} placeholder="z. B. automatische Verlängerung um 12 Monate" /></label>
            <label>Vertragsdokument<select name="document_id" defaultValue=""><option value="">Kein Dokument zuordnen</option>
              {documents.map((item) => <option key={item.id} value={item.id}>{item.document_number} · {item.title}</option>)}
            </select></label>
            <label>Interne Notizen<textarea name="internal_notes" rows={2} maxLength={10000} /></label>
            <button type="submit" disabled={busy || (canReadCustomers && customers.length === 0)}>{busy ? "Wird gespeichert …" : "Vertrag speichern"}</button>
          </form>
        </section>}
        {selectedContract && <section className="panel detail-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">VERTRAG · {selectedContract.contract_number}</p><h2>{selectedContract.name}</h2></div>
            <button className="secondary-button" onClick={() => setSelectedContract(null)}>Schließen</button>
          </div>
          {canUpdateContracts && !selectedContract.archived_at ? <form className="contract-edit-form" onSubmit={(event) => void saveContract(event)}>
            <div className="form-row">
              <label>Nummer<input name="contract_number" required defaultValue={selectedContract.contract_number} /></label>
              <label>Name<input name="name" required defaultValue={selectedContract.name} /></label>
              <label>Typ<select name="contract_type" defaultValue={selectedContract.contract_type}>{Object.entries(contractTypes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
              <label>Vertragspartner<input name="counterparty" required defaultValue={selectedContract.counterparty} /></label>
              <label>Status<select name="status" defaultValue={selectedContract.status}>
                {Object.entries(contractStatuses).filter(([key]) => key !== "archived").map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </select></label>
              <label>Beginn<input name="starts_on" type="date" required defaultValue={selectedContract.starts_on} /></label>
              <label>Ende<input name="ends_on" type="date" defaultValue={selectedContract.ends_on ?? ""} /></label>
              <label>Kündigungsfrist (Tage)<input name="notice_period_days" type="number" min="0" max="3650" defaultValue={selectedContract.notice_period_days ?? ""} /></label>
            </div>
            <label>Verlängerungsregel<textarea name="renewal_rule" rows={2} defaultValue={selectedContract.renewal_rule ?? ""} /></label>
            <label>Interne Notizen<textarea name="internal_notes" rows={2} defaultValue={selectedContract.internal_notes ?? ""} /></label>
            <button type="submit" disabled={busy}>Vertrag speichern</button>
          </form> : <div className="detail-summary">
            <p><strong>Typ:</strong> {contractTypes[selectedContract.contract_type]}</p>
            <p><strong>Vertragspartner:</strong> {selectedContract.counterparty}</p>
            <p><strong>Laufzeit:</strong> {dateLabel(selectedContract.starts_on)} – {dateLabel(selectedContract.ends_on)}</p>
            <p><strong>Status:</strong> {contractStatuses[selectedContract.status]}</p>
            <p><strong>Verlängerungsregel:</strong> {selectedContract.renewal_rule || "—"}</p>
            {selectedContract.internal_notes && <p><strong>Interne Notizen:</strong> {selectedContract.internal_notes}</p>}
          </div>}
          {canArchiveContracts && <div className="archive-box contract-archive-box">
            <h3>{selectedContract.archived_at ? "Archivierter Vertrag" : "Vertrag archivieren"}</h3>
            <p className="muted">Archivierung löscht weder den Vertrag noch das zugehörige Dokument.</p>
            <button className={selectedContract.archived_at ? "primary-button" : "danger-button"} disabled={busy}
              onClick={() => void archiveSelectedContract()}>{selectedContract.archived_at ? "Wiederherstellen" : "Archivieren"}</button>
          </div>}
          <section className="history-section">
            <h3>Vertragschronik</h3>
            {!selectedContract.history.length ? <p className="muted">Noch keine Chronikeinträge.</p> : <ol className="history-list">
              {selectedContract.history.map((item) => <li key={item.id}>
                <strong>{contractActionName(item.action)}</strong><time>{dateTimeLabel(item.created_at)}</time>
                {!!item.changed_fields.length && <small>Geänderte Bereiche: {item.changed_fields.join(", ")}</small>}
              </li>)}
            </ol>}
          </section>
        </section>}
      </>}

      {tab === "reminders" && <section className="panel">
        <div className="panel-heading">
          <div><p className="eyebrow">FRISTEN</p><h2>Vertrags- und Dokumenterinnerungen</h2></div>
          {canManageReminders && <button className="secondary-button" disabled={busy || loading} onClick={() => void refreshReminders()}>Erinnerungen aktualisieren</button>}
        </div>
        <p className="muted">Die Planung ist idempotent und konkurrierende Aktualisierungen werden per Datenbank-Constraints dedupliziert. Benachrichtigungen werden hier im System angezeigt.</p>
        {canManageReminders && reminderSettings && <form className="reminder-settings-form" onSubmit={(event) => void saveReminderSettings(event)}>
          <label>Vorlaufzeiten in Tagen, durch Komma getrennt
            <input name="lead_days" defaultValue={reminderSettings.lead_days.join(", ")} aria-label="Vorlaufzeiten in Tagen" />
          </label>
          <button className="secondary-button" type="submit" disabled={busy}>Vorlaufzeiten speichern</button>
        </form>}
        {loading ? <p className="muted">Erinnerungen werden geladen …</p> : reminders.length ? (
          <div className="table-scroll"><table><thead><tr><th>Erinnerung</th><th>Frist</th><th>Vorlauf</th><th>Status</th><th></th></tr></thead>
            <tbody>{reminders.map((item) => <tr key={item.id}>
              <td><strong>{item.subject}</strong><small>{item.number} · {reminderNames[item.reminder_type]}</small></td>
              <td>{dateLabel(item.event_on)}</td><td>{dateLabel(item.remind_on)}</td>
              <td><span className={item.remind_on <= new Date().toISOString().slice(0, 10) ? "status status-warning" : "status"}>{item.remind_on <= new Date().toISOString().slice(0, 10) ? "Fällig" : "Geplant"}</span></td>
              <td>{canManageReminders && <div className="version-actions">
                <button className="text-button" disabled={busy} onClick={() => void markReminder(item, "completed")}>Erledigt</button>
                <button className="text-button" disabled={busy} onClick={() => void markReminder(item, "dismissed")}>Verwerfen</button>
              </div>}</td>
            </tr>)}</tbody></table>
          </div>
        ) : <p className="muted">Keine offenen Erinnerungen. Aktualisiere die Planung, um neue Fristen zu erzeugen.</p>}
      </section>}
    </section>
  );
}

function AssignmentFields({
  customers,
  objects,
  employees,
  contractType,
}: {
  customers: Customer[];
  objects: ObjectPage["items"];
  employees: Employee[];
  contractType?: ContractType;
}) {
  return (
    <div className="assignment-fields">
      {contractType && ["object", "service"].includes(contractType) && <label>Objekt (optional)<select name="object_id" defaultValue="">
        <option value="">Kein Objekt</option>{objects.map((item) =>
          <option key={item.id} value={item.id}>{item.code} · {item.name}</option>,
        )}
      </select></label>}
      {contractType === "personnel" && <label>Mitarbeiter (optional)
        <select name="employee_id" defaultValue="">
          <option value="">Keine Zuordnung</option>{employees.map((item) =>
            <option key={item.id} value={item.id}>{item.employee_number} · {item.full_name}</option>,
          )}
        </select>
      </label>}
      {!contractType && <>
        <label>Mitarbeiterzuordnung (optional)
          <select name="employee_id" defaultValue="">
            <option value="">Keine Zuordnung</option>{employees.map((item) =>
              <option key={item.id} value={item.id}>{item.employee_number} · {item.full_name}</option>,
            )}
          </select>
        </label>
        <label>Kunde (optional)<select name="customer_id" defaultValue=""><option value="">Kein Kunde</option>
          {customers.map((item) => <option key={item.id} value={item.id}>{item.customer_number} · {item.company_name}</option>)}
        </select></label>
        <label>Objekt (optional)<select name="object_id" defaultValue=""><option value="">Kein Objekt</option>
          {objects.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}
        </select></label>
      </>}
    </div>
  );
}

function documentActionName(action: string) {
  const names: Record<string, string> = {
    created: "Dokument angelegt und hochgeladen",
    updated: "Metadaten geändert",
    archived: "Dokument archiviert",
    restored: "Dokument wiederhergestellt",
    version_uploaded: "Neue Version hochgeladen",
    approval_requested: "Freigabe angefordert",
    approval_approved: "Version freigegeben",
    approval_rejected: "Freigabe abgelehnt",
    read_confirmed: "Lesebestätigung erfasst",
  };
  return names[action] ?? action;
}

function contractActionName(action: string) {
  const names: Record<string, string> = {
    created: "Vertrag angelegt",
    updated: "Vertrag geändert",
    archived: "Vertrag archiviert",
    restored: "Vertrag wiederhergestellt",
  };
  return names[action] ?? action;
}
