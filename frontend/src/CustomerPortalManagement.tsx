import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createCustomerPortalLink,
  addManagedCustomerPortalRequestMessage,
  downloadManagedCustomerPortalRequestAttachment,
  getCustomerPortalDocumentCandidates,
  getCustomerPortalDocumentGrants,
  getCustomerPortalAccessHistory,
  getCustomerPortalLinkHistory,
  getCustomerPortalLinks,
  getCustomerPortalManagementOptions,
  getManagedCustomerPortalRequests,
  grantCustomerPortalDocument,
  revokeCustomerPortalDocument,
  setCustomerPortalLinkActive,
  unlinkCustomerPortalContact,
  updateManagedCustomerPortalRequestStatus,
} from "./api";
import type {
  CustomerPortalDocumentCandidate,
  CustomerPortalDocumentGrant,
  CustomerPortalAccessEvent,
  CustomerPortalLink,
  CustomerPortalLinkHistory,
  CustomerPortalManagementOptions,
  CustomerPortalRequest,
} from "./types";

function messageFrom(reason: unknown) {
  return reason instanceof Error ? reason.message : "Die Kundenportalverwaltung ist fehlgeschlagen.";
}

function portalActionLabel(action: string) {
  const labels: Record<string, string> = {
    "customer_portal.linked": "Zugang verknüpft",
    "customer_portal.unlinked": "Zugang gelöst",
    "customer_portal.activated": "Zugang aktiviert",
    "customer_portal.deactivated": "Zugang deaktiviert",
    "customer_portal.document_granted": "Dokument freigegeben",
    "customer_portal.document_revoked": "Dokumentfreigabe widerrufen",
    "customer_portal.document_downloaded": "Dokument heruntergeladen",
    "customer_portal.invoice.downloaded": "Rechnung heruntergeladen",
    "customer_portal.profile_viewed": "Kundenprofil eingesehen",
    "customer_portal.invoices_viewed": "Rechnungsübersicht eingesehen",
    "customer_portal.documents_viewed": "Dokumentübersicht eingesehen",
    "customer_portal.requests_viewed": "Vorgangsübersicht eingesehen",
    "customer_portal.request_viewed": "Vorgang eingesehen",
    "customer_portal.request_created": "Vorgang angelegt",
    "customer_portal.request_message_added": "Nachricht hinzugefügt",
    "customer_portal.request_attachment_added": "Anhang hinzugefügt",
    "customer_portal.request_attachment_downloaded": "Anhang heruntergeladen",
    "customer_portal.request_status_changed": "Vorgangsstatus geändert",
  };
  return labels[action] ?? "Portalaktivität";
}

function requestHistoryLabel(action: string) {
  const labels: Record<string, string> = {
    created: "Anfrage angelegt",
    message_added: "Nachricht hinzugefügt",
    attachment_added: "Anhang hinzugefügt",
    status_changed: "Status geändert",
  };
  return labels[action] ?? "Vorgangsänderung";
}

export default function CustomerPortalManagement({
  canManageRequests,
  canManageDocuments,
}: {
  canManageRequests: boolean;
  canManageDocuments: boolean;
}) {
  const [links, setLinks] = useState<CustomerPortalLink[]>([]);
  const [history, setHistory] = useState<CustomerPortalLinkHistory[]>([]);
  const [accessHistory, setAccessHistory] = useState<CustomerPortalAccessEvent[]>([]);
  const [options, setOptions] = useState<CustomerPortalManagementOptions>({
    users: [],
    contacts: [],
  });
  const [candidates, setCandidates] = useState<CustomerPortalDocumentCandidate[]>([]);
  const [grants, setGrants] = useState<CustomerPortalDocumentGrant[]>([]);
  const [requests, setRequests] = useState<CustomerPortalRequest[]>([]);
  const [selectedDocument, setSelectedDocument] = useState("");
  const [selectedUser, setSelectedUser] = useState("");
  const [selectedContact, setSelectedContact] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const reload = useCallback(async () => {
    const [
      currentLinks,
      currentOptions,
      currentHistory,
      currentAccessHistory,
      currentCandidates,
      currentRequests,
    ] = await Promise.all([
      getCustomerPortalLinks(),
      getCustomerPortalManagementOptions(),
      getCustomerPortalLinkHistory(),
      getCustomerPortalAccessHistory(),
      canManageDocuments ? getCustomerPortalDocumentCandidates() : Promise.resolve([]),
      canManageRequests ? getManagedCustomerPortalRequests() : Promise.resolve([]),
    ]);
    setLinks(currentLinks);
    setOptions(currentOptions);
    setHistory(currentHistory);
    setAccessHistory(currentAccessHistory);
    setCandidates(currentCandidates);
    setRequests(currentRequests);
    setSelectedDocument((current) =>
      currentCandidates.some((candidate) => candidate.document_id === current)
        ? current
        : currentCandidates[0]?.document_id ?? "",
    );
  }, [canManageDocuments, canManageRequests]);

  useEffect(() => {
    let active = true;
    reload()
      .catch((reason: unknown) => {
        if (active) setError(messageFrom(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [reload]);

  useEffect(() => {
    if (!selectedDocument) {
      setGrants([]);
      return;
    }
    let active = true;
    getCustomerPortalDocumentGrants(selectedDocument)
      .then((items) => {
        if (active) setGrants(items);
      })
      .catch((reason: unknown) => {
        if (active) setError(messageFrom(reason));
      });
    return () => {
      active = false;
    };
  }, [selectedDocument]);

  const linkedUserIds = useMemo(() => new Set(links.map((link) => link.user_id)), [links]);
  const linkedContactIds = useMemo(() => new Set(links.map((link) => link.contact_id)), [links]);
  const availableUsers = options.users.filter((item) => !linkedUserIds.has(item.id));
  const availableContacts = options.contacts.filter((item) => !linkedContactIds.has(item.id));
  const chosenCandidate = candidates.find((candidate) => candidate.document_id === selectedDocument);

  async function perform(action: string, operation: () => Promise<unknown>) {
    setBusy(action);
    setError("");
    setNotice("");
    try {
      await operation();
      await reload();
      if (selectedDocument) setGrants(await getCustomerPortalDocumentGrants(selectedDocument));
      setNotice("Änderungen wurden gespeichert.");
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy("");
    }
  }

  async function createLink(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedUser || !selectedContact) return;
    await perform("link", () => createCustomerPortalLink(selectedUser, selectedContact));
  }

  async function grantDocument() {
    if (!chosenCandidate) return;
    await perform("grant", () =>
      grantCustomerPortalDocument(chosenCandidate.document_id, chosenCandidate.version_id),
    );
  }

  async function sendAdminReply(requestId: string, body: string) {
    await perform("reply", () => addManagedCustomerPortalRequestMessage(requestId, body));
  }

  async function downloadRequestAttachment(
    requestItem: CustomerPortalRequest,
    attachmentId: string,
    fileName: string,
  ) {
    try {
      const blob = await downloadManagedCustomerPortalRequestAttachment(requestItem.id, attachmentId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(messageFrom(reason));
    }
  }

  if (loading) return <p className="muted">Kundenportalverwaltung wird geladen …</p>;

  return (
    <section className="management-module" aria-labelledby="portal-management-title">
      <header className="intro">
        <p className="eyebrow">KUNDENPORTAL</p>
        <h1 id="portal-management-title">Zugänge und Freigaben</h1>
        <p>Verknüpfungen, Aktivierung und ausdrücklich freigegebene Kundendokumente verwalten.</p>
      </header>
      {error && <p className="alert page-alert" role="alert">{error}</p>}
      {notice && <p className="success page-alert" role="status">{notice}</p>}

      <section className="panel" aria-labelledby="portal-links-title">
        <div className="panel-heading">
          <div><p className="eyebrow">ZUGÄNGE</p><h2 id="portal-links-title">Benutzer und Ansprechpartner</h2></div>
        </div>
        <form className="form-grid" onSubmit={(event) => void createLink(event)}>
          <label>Portal-Benutzerkonto
            <select value={selectedUser} onChange={(event) => setSelectedUser(event.target.value)} required>
              <option value="">Konto auswählen</option>
              {availableUsers.map((item) => (
                <option key={item.id} value={item.id}>{item.full_name} ({item.username})</option>
              ))}
            </select>
          </label>
          <label>Kundenkontakt
            <select value={selectedContact} onChange={(event) => setSelectedContact(event.target.value)} required>
              <option value="">Kontakt auswählen</option>
              {availableContacts.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.customer_name} · {item.first_name} {item.last_name}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={!selectedUser || !selectedContact || busy !== ""}>
            {busy === "link" ? "Wird verknüpft …" : "Manuell verknüpfen"}
          </button>
        </form>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Benutzer-ID</th><th>Kontakt-ID</th><th>Status</th><th>Aktionen</th></tr></thead>
            <tbody>{links.map((link) => (
              <tr key={link.id}>
                <td>{link.user_id}</td>
                <td>{link.contact_id}</td>
                <td>{link.is_active ? "Aktiv" : "Deaktiviert"}</td>
                <td className="button-row">
                  <button
                    type="button"
                    disabled={busy !== ""}
                    onClick={() => void perform(
                      "state",
                      () => setCustomerPortalLinkActive(link.contact_id, !link.is_active),
                    )}
                  >{link.is_active ? "Deaktivieren" : "Aktivieren"}</button>
                  <button
                    type="button"
                    disabled={busy !== ""}
                    onClick={() => {
                      if (window.confirm("Portalverknüpfung dauerhaft lösen? Die Historie bleibt erhalten.")) {
                        void perform("unlink", () => unlinkCustomerPortalContact(link.contact_id));
                      }
                    }}
                  >Lösen</button>
                </td>
              </tr>
            ))}</tbody>
          </table>
          {links.length === 0 && <p className="muted">Es bestehen keine Portalverknüpfungen.</p>}
        </div>
      </section>

      <section className="panel" aria-labelledby="portal-link-history-title">
        <div className="panel-heading">
          <div><p className="eyebrow">ZUGRIFFSHISTORIE</p><h2 id="portal-link-history-title">Verknüpfungsänderungen</h2></div>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Zeitpunkt</th><th>Aktion</th><th>Benutzer-ID</th><th>Kontakt-ID</th><th>Ausgeführt durch</th></tr></thead>
            <tbody>{history.map((item, index) => (
              <tr key={`${item.created_at}-${index}`}>
                <td>{new Date(item.created_at).toLocaleString("de-DE")}</td>
                <td>{{
                  linked: "Verknüpft",
                  unlinked: "Gelöst",
                  activated: "Aktiviert",
                  deactivated: "Deaktiviert",
                }[item.action]}</td>
                <td>{item.user_id}</td>
                <td>{item.contact_id}</td>
                <td>{item.actor_id ?? "Nicht mehr vorhanden"}</td>
              </tr>
            ))}</tbody>
          </table>
          {history.length === 0 && <p className="muted">Noch keine Änderungen protokolliert.</p>}
        </div>
      </section>

      <section className="panel" aria-labelledby="portal-access-history-title">
        <div className="panel-heading">
          <div><p className="eyebrow">PORTALZUGRIFFE</p><h2 id="portal-access-history-title">Aktivitäten (Metadaten)</h2></div>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Zeitpunkt</th><th>Aktion</th><th>Datensatztyp</th><th>Datensatz-ID</th><th>Akteur-ID</th></tr></thead>
            <tbody>{accessHistory.map((event, index) => (
              <tr key={`${event.created_at}-${index}`}>
                <td>{new Date(event.created_at).toLocaleString("de-DE")}</td>
                <td>{portalActionLabel(event.action)}</td>
                <td>{event.entity_type}</td>
                <td>{event.entity_id ?? "—"}</td>
                <td>{event.actor_id ?? "Nicht mehr vorhanden"}</td>
              </tr>
            ))}</tbody>
          </table>
          {accessHistory.length === 0 && <p className="muted">Noch keine Portalaktivitäten protokolliert.</p>}
        </div>
      </section>

      {canManageDocuments && <section className="panel" aria-labelledby="portal-doc-grants-title">
        <div className="panel-heading">
          <div><p className="eyebrow">DOKUMENTFREIGABEN</p><h2 id="portal-doc-grants-title">Kundenunterlagen veröffentlichen</h2></div>
        </div>
        {candidates.length === 0
          ? <p className="muted">Keine aktiven, nicht personenbezogenen Kundendokumente vorhanden.</p>
          : <>
            <label>Dokument
              <select value={selectedDocument} onChange={(event) => setSelectedDocument(event.target.value)}>
                {candidates.map((candidate) => (
                  <option key={candidate.document_id} value={candidate.document_id}>
                    {candidate.customer_name} · {candidate.title} · Version {candidate.version}
                  </option>
                ))}
              </select>
            </label>
            {chosenCandidate && <p className="muted">
              {chosenCandidate.document_number} · {chosenCandidate.file_name}
            </p>}
            <button type="button" disabled={!chosenCandidate || busy !== ""} onClick={() => void grantDocument()}>
              {busy === "grant" ? "Wird freigegeben …" : "Aktuelle Version freigeben"}
            </button>
            <div className="table-scroll">
              <table>
                <thead><tr><th>Freigegeben am</th><th>Freigegeben durch</th><th>Status</th><th>Widerrufen am</th><th>Aktion</th></tr></thead>
                <tbody>{grants.map((grant) => (
                  <tr key={grant.id}>
                    <td>{new Date(grant.granted_at).toLocaleString("de-DE")}</td>
                    <td>{grant.granted_by_id ?? "Nicht mehr vorhanden"}</td>
                    <td>{grant.revoked_at ? "Widerrufen" : "Aktiv"}</td>
                    <td>{grant.revoked_at ? new Date(grant.revoked_at).toLocaleString("de-DE") : "—"}</td>
                    <td>{!grant.revoked_at && <button
                      type="button"
                      disabled={busy !== ""}
                      onClick={() => void perform("revoke", () => revokeCustomerPortalDocument(grant.id))}
                    >Widerrufen</button>}</td>
                  </tr>
                ))}</tbody>
              </table>
              {grants.length === 0 && <p className="muted">Dieses Dokument wurde noch nicht freigegeben.</p>}
            </div>
          </>}
      </section>}

      {canManageRequests && <section className="panel" aria-labelledby="portal-request-admin-title">
        <div className="panel-heading">
          <div><p className="eyebrow">ANFRAGENVERWALTUNG</p><h2 id="portal-request-admin-title">Rückfragen und Beschwerden</h2></div>
        </div>
        {requests.length === 0
          ? <p className="muted">Es liegen keine Kundenanfragen vor.</p>
          : <div className="content-grid">
            {requests.map((item) => (
              <article className="panel" key={item.id}>
                <div className="panel-heading">
                  <div>
                    <h3>{item.title}</h3>
                    <p className="muted">{item.customer_name} · {item.object_name} · {
                      item.category === "complaint"
                        ? "Beschwerde"
                        : item.category === "request" ? "Anfrage" : "Rückfrage"
                    }</p>
                  </div>
                  <select
                    aria-label={`Status für ${item.title}`}
                    value={item.status}
                    disabled={busy !== ""}
                    onChange={(event) => void perform(
                      "request-status",
                      () => updateManagedCustomerPortalRequestStatus(
                        item.id,
                        event.target.value as CustomerPortalRequest["status"],
                      ),
                    )}
                  >
                    <option value="submitted">Eingegangen</option>
                    <option value="in_progress">In Bearbeitung</option>
                    <option value="waiting_customer">Rückfrage an Kunde</option>
                    <option value="resolved">Gelöst</option>
                    <option value="closed">Geschlossen</option>
                  </select>
                </div>
                {item.messages.map((message) => (
                  <p key={message.id}>
                    <strong>{message.author_id ? `Konto ${message.author_id}` : "Konto nicht mehr vorhanden"}:</strong> {message.body}
                  </p>
                ))}
                {item.attachments.map((attachment) => (
                  <button
                    type="button"
                    className="text-button"
                    key={attachment.id}
                    onClick={() => void downloadRequestAttachment(item, attachment.id, attachment.file_name)}
                  >Kundenanhang laden: {attachment.file_name}</button>
                ))}
                <form className="form-grid" onSubmit={(event) => {
                  event.preventDefault();
                  const form = event.currentTarget;
                  const body = String(new FormData(form).get("admin_reply") ?? "").trim();
                  if (body) void sendAdminReply(item.id, body).then(() => form.reset());
                }}>
                  <label>Antwort an den Kunden<textarea name="admin_reply" maxLength={4000} required /></label>
                  <button type="submit" disabled={busy !== ""}>Antwort senden</button>
                </form>
                <details>
                  <summary>Vorgangsverlauf</summary>
                  <ul>{item.history.map((event, index) => (
                    <li key={`${event.created_at}-${index}`}>
                      {new Date(event.created_at).toLocaleString("de-DE")} · {requestHistoryLabel(event.action)}
                      {event.old_status && event.new_status
                        ? ` (${event.old_status} → ${event.new_status})`
                        : ""}
                    </li>
                  ))}</ul>
                </details>
              </article>
            ))}
          </div>}
      </section>}
    </section>
  );
}
