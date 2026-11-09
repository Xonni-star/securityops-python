import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  archiveCustomer,
  changePassword,
  createCustomer,
  createCustomerContact,
  deleteCustomerContact,
  getCustomer,
  getCustomerObjects,
  getCustomerHistory,
  getCustomers,
  getDashboard,
  getSession,
  login,
  logout,
  reactivateCustomer,
  updateCustomer,
  updateCustomerContact,
} from "./api";
import ObjectManagement from "./ObjectManagement";
import DocumentContractManagement from "./DocumentContractManagement";
import PersonnelManagement from "./PersonnelManagement";
import SchedulingManagement from "./SchedulingManagement";
import TimeTracking from "./TimeTracking";
import OWKSManagement from "./OWKSManagement";
import BillingManagement from "./BillingManagement";
import IdentitySecurity from "./IdentitySecurity";
import TaskManagement from "./TaskManagement";
import NotificationManagement from "./NotificationManagement";
import AutomationManagement from "./AutomationManagement";
import KeyManagement from "./KeyManagement";
import InventoryManagement from "./InventoryManagement";
import IncidentManagement from "./IncidentManagement";
import ControlRoom from "./ControlRoom";
import EmployeePortal from "./EmployeePortal";
import CustomerPortal from "./CustomerPortal";
import CustomerPortalManagement from "./CustomerPortalManagement";
import GlobalSearch from "./GlobalSearch";
import type {
  AuthUser,
  Customer,
  CustomerAddress,
  CustomerAddressInput,
  CustomerContractStatus,
  CustomerHistory,
  CustomerSort,
  CustomerStatus,
  Dashboard,
  GlobalSearchEntityType,
  GlobalSearchResult,
  SecurityObject,
} from "./types";

const statusNames: Record<CustomerStatus, string> = {
  active: "Aktiv",
  inactive: "Inaktiv",
  lead: "Interessent",
};

const contractStatusNames: Record<CustomerContractStatus, string> = {
  none: "Kein Vertrag",
  draft: "In Vorbereitung",
  active: "Aktiv",
  expired: "Abgelaufen",
  terminated: "Beendet",
};

const objectStatusNames = {
  active: "Aktiv",
  inactive: "Inaktiv",
} as const;

const actionNames: Record<string, string> = {
  created: "Kunde angelegt",
  updated: "Kundendaten geändert",
  archived: "Kunde archiviert",
  reactivated: "Kunde reaktiviert",
  contact_created: "Ansprechpartner hinzugefügt",
  contact_updated: "Ansprechpartner geändert",
  contact_deleted: "Ansprechpartner entfernt",
};

const pageSize = 25;
type ActiveModule =
  | "employee_portal"
  | "customers"
  | "control_room"
  | "objects"
  | "employees"
  | "scheduling"
  | "time_tracking"
  | "documents"
  | "billing"
  | "owks"
  | "tasks"
  | "notifications"
  | "automations"
  | "keys"
  | "inventory"
  | "incidents"
  | "customer_portal"
  | "security";

function messageFrom(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function optionalValue(data: FormData, name: string) {
  return String(data.get(name) ?? "").trim() || undefined;
}

function formAddress(data: FormData, prefix: string): CustomerAddressInput | undefined {
  const street = optionalValue(data, `${prefix}_street`);
  const houseNumber = optionalValue(data, `${prefix}_house_number`);
  const postalCode = optionalValue(data, `${prefix}_postal_code`);
  const city = optionalValue(data, `${prefix}_city`);
  if (!street && !houseNumber && !postalCode && !city) return undefined;
  return {
    street: street ?? "",
    house_number: houseNumber ?? "",
    postal_code: postalCode ?? "",
    city: city ?? "",
    country_code: optionalValue(data, `${prefix}_country_code`)?.toUpperCase() || "DE",
  };
}

function AddressFields({ prefix, title, address }: {
  prefix: string;
  title: string;
  address?: CustomerAddress | null;
}) {
  return (
    <fieldset className="address-fields">
      <legend>{title}</legend>
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

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [passwordChangeRequired, setPasswordChangeRequired] = useState(false);
  const moduleSelectedManually = useRef(false);
  const [authLoading, setAuthLoading] = useState(true);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [matchingCustomers, setMatchingCustomers] = useState(0);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<CustomerStatus | "">("");
  const [contractStatusFilter, setContractStatusFilter] = useState<CustomerContractStatus | "">("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [sortBy, setSortBy] = useState<CustomerSort>("company_name");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [offset, setOffset] = useState(0);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [history, setHistory] = useState<CustomerHistory[]>([]);
  const [customerObjects, setCustomerObjects] = useState<SecurityObject[]>([]);
  const [initialObjectId, setInitialObjectId] = useState<string | null>(null);
  const [searchResult, setSearchResult] = useState<GlobalSearchResult | null>(null);
  const [activeModule, setActiveModule] = useState<ActiveModule>("customers");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const canReadCustomers = user?.permissions.includes("customers.read") ?? false;
  const canCreateCustomers = user?.permissions.includes("customers.create") ?? false;
  const canUpdateCustomers = user?.permissions.includes("customers.update") ?? false;
  const canArchiveCustomers = user?.permissions.includes("customers.archive") ?? false;
  const canReadObjects = user?.permissions.includes("objects.read") ?? false;
  const canReadEmployees = user?.permissions.includes("employees.read") ?? false;
  const isEmployeePortal = Boolean(
    user?.roles.includes("employee") && !canReadEmployees,
  );
  const canReadScheduling = user?.permissions.includes("scheduling.read") ?? false;
  const canReadTimeTracking = user?.permissions.some((permission) =>
    ["time_tracking.read_own", "time_tracking.read_all"].includes(permission),
  ) ?? false;
  const canAccessDocuments = user?.permissions.some((permission) =>
    ["documents.read", "documents.create", "contracts.read", "contracts.create"].includes(permission),
  ) ?? false;
  const canReadOWKS = user?.permissions.includes("owks.read") ?? false;
  const canAccessBilling = user?.permissions.includes("billing.invoices.read") ?? false;
  const canReadTasks = user?.permissions.some((permission) =>
    ["tasks.read_own", "tasks.read_all", "tasks.manage_all"].includes(permission),
  ) ?? false;
  const canCreateTasks = user?.permissions.includes("tasks.create") ?? false;
  const canReadNotifications = Boolean(
    user?.permissions.includes("notifications.read_own") && (canReadTasks || canReadOWKS),
  );
  const canManageAutomations = user?.permissions.includes("automations.manage") ?? false;
  const canReadKeys = user?.permissions.includes("keys.read") ?? false;
  const canReadInventory = user?.permissions.includes("inventory.read") ?? false;
  const canManageInventory = user?.permissions.includes("inventory.manage") ?? false;
  const canMoveInventory = user?.permissions.includes("inventory.move") ?? false;
  const canManageCustomerPortal = user?.permissions.includes("customers.portal.manage") ?? false;
  const canManageCustomerPortalRequests =
    user?.permissions.includes("customer_portal.requests.manage") ?? false;
  const canManageCustomerPortalDocuments =
    user?.permissions.includes("customer_portal.documents.manage") ?? false;
  const canManageKeys = user?.permissions.includes("keys.manage") ?? false;
  const canMoveKeys = user?.permissions.includes("keys.move") ?? false;
  const canAccessIncidents = user?.permissions.some((permission) =>
    ["incidents.read", "incidents.read_all", "incidents.manage_all", "incidents.create"].includes(permission),
  ) ?? false;
  const permissions = user?.permissions ?? [];
  const searchableTypes: GlobalSearchEntityType[] = [
    ...(canReadCustomers ? ["customer" as const] : []),
    ...(canReadObjects ? ["object" as const] : []),
    ...(canReadEmployees ? ["employee" as const] : []),
    ...(permissions.includes("documents.read") ? ["document" as const] : []),
    ...(permissions.includes("contracts.read") ? ["contract" as const] : []),
    ...(canReadScheduling ? ["shift" as const] : []),
    ...(permissions.some((permission) =>
      ["tasks.read_own", "tasks.read_all", "tasks.manage_all"].includes(permission),
    ) ? ["task" as const] : []),
    ...(permissions.some((permission) =>
      ["incidents.read", "incidents.read_all", "incidents.manage_all"].includes(permission),
    ) ? ["incident" as const] : []),
    ...(canReadKeys ? ["key" as const] : []),
    ...(canReadInventory ? ["inventory_asset" as const] : []),
    ...(canReadOWKS ? ["owks_event" as const] : []),
  ];

  useEffect(() => {
    getSession()
      .then((session) => {
        setUser(session.user);
        setPasswordChangeRequired(session.password_change_required ?? false);
      })
      .catch(() => {
        setUser(null);
        setPasswordChangeRequired(false);
      })
      .finally(() => setAuthLoading(false));
  }, []);

  const loadData = useCallback(async () => {
    try {
      const [page, stats] = await Promise.all([
        canReadCustomers
          ? getCustomers({
            q: search,
            status: statusFilter,
            contractStatus: contractStatusFilter,
            includeArchived,
            sortBy,
            sortOrder,
            limit: pageSize,
            offset,
          })
          : Promise.resolve(null),
        user?.permissions.includes("dashboard.read") ? getDashboard() : Promise.resolve(null),
      ]);
      setCustomers(page?.items ?? []);
      setMatchingCustomers(page?.total ?? 0);
      setDashboard(stats);
      setError("");
    } catch (reason) {
      setError(messageFrom(reason, "Daten konnten nicht geladen werden."));
    }
  }, [canReadCustomers, contractStatusFilter, includeArchived, offset, search, sortBy, sortOrder, statusFilter, user]);

  const refreshSelected = useCallback(async (customerId: string) => {
    const [customer, customerHistory, objectPage] = await Promise.all([
      getCustomer(customerId),
      getCustomerHistory(customerId),
      canReadObjects
        ? getCustomerObjects(customerId)
        : Promise.resolve({ items: [] as SecurityObject[] }),
    ]);
    setSelectedCustomer(customer);
    setHistory(customerHistory);
    setCustomerObjects(objectPage.items);
    return customer;
  }, [canReadObjects]);

  useEffect(() => {
    if (user) void loadData();
  }, [loadData, user]);

  useEffect(() => {
    if (moduleSelectedManually.current) return;
    if (isEmployeePortal) setActiveModule("employee_portal");
    else if (user?.permissions.includes("control_room.read")) setActiveModule("control_room");
    else if (user && !canReadCustomers && canReadObjects) setActiveModule("objects");
    else if (user && !canReadCustomers && !canReadObjects && canReadKeys) {
      setActiveModule("keys");
    }
    else if (user && !canReadCustomers && !canReadObjects && !canReadKeys && canReadInventory) {
      setActiveModule("inventory");
    }
    else if (user && !canReadCustomers && !canReadObjects && canReadEmployees) {
      setActiveModule("employees");
    } else if (user && !canReadCustomers && !canReadObjects && !canReadEmployees && canReadScheduling) {
      setActiveModule("scheduling");
    } else if (
      user && !canReadCustomers && !canReadObjects && !canReadEmployees
      && !canReadScheduling && canReadTimeTracking
    ) {
      setActiveModule("time_tracking");
    } else if (
      user && !canReadCustomers && !canReadObjects && !canReadEmployees
      && !canReadScheduling && !canReadTimeTracking && canAccessBilling
    ) {
      setActiveModule("billing");
    }
    else if (
      user && !canReadCustomers && !canReadObjects && !canReadEmployees
      && !canReadScheduling && !canReadTimeTracking && canAccessDocuments
    ) {
      setActiveModule("documents");
    }
    else if (
      user && !canReadCustomers && !canReadObjects && !canReadEmployees
      && !canReadScheduling && !canReadTimeTracking && !canAccessDocuments && !canAccessBilling && canReadOWKS
    ) {
      setActiveModule("owks");
    }
    else if (
      user && !canReadCustomers && !canReadObjects && !canReadEmployees
      && !canReadScheduling && !canReadTimeTracking && !canAccessDocuments && !canAccessBilling
      && !canReadOWKS && (canReadTasks || canCreateTasks)
    ) {
      setActiveModule("tasks");
    }
    else if (
      user && !canReadCustomers && !canReadObjects && !canReadEmployees
      && !canReadScheduling && !canReadTimeTracking && !canAccessDocuments && !canAccessBilling
      && !canReadOWKS && !canReadTasks && !canCreateTasks && canReadNotifications
    ) {
      setActiveModule("notifications");
    }
    else if (
      user && !canReadCustomers && !canReadObjects && !canReadEmployees
      && !canReadScheduling && !canReadTimeTracking && !canAccessDocuments && !canAccessBilling
      && !canReadOWKS && !canReadTasks && !canCreateTasks && !canReadNotifications
      && canManageAutomations
    ) {
      setActiveModule("automations");
    }
  }, [canAccessBilling, canAccessDocuments, canCreateTasks, canManageAutomations, canReadCustomers, canReadEmployees, canReadInventory, canReadKeys, canReadNotifications, canReadObjects, canReadOWKS, canReadScheduling, canReadTasks, canReadTimeTracking, isEmployeePortal, user]);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const factor = String(data.get("mfa_factor") ?? "").trim();
    setBusy(true);
    try {
      const session = await login(
        String(data.get("username")),
        String(data.get("password")),
        /^\d{6}$/.test(factor)
          ? { mfa_code: factor }
          : factor ? { recovery_code: factor } : undefined,
      );
      moduleSelectedManually.current = false;
      setUser(session.user);
      setPasswordChangeRequired(session.password_change_required ?? false);
      setError("");
    } catch (reason) {
      setError(messageFrom(reason, "Anmeldung fehlgeschlagen."));
    } finally {
      setBusy(false);
    }
  }

  async function submitRequiredPasswordChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const currentPassword = String(data.get("current_password"));
    const newPassword = String(data.get("new_password"));
    if (newPassword !== String(data.get("confirm_password"))) {
      setError("Die neuen Passwörter stimmen nicht überein.");
      return;
    }
    setBusy(true);
    try {
      await changePassword(currentPassword, newPassword);
      setUser(null);
      setPasswordChangeRequired(false);
      setError("");
    } catch (reason) {
      setError(messageFrom(reason, "Passwort konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  function clearLocalSession() {
    moduleSelectedManually.current = false;
    setUser(null);
    setPasswordChangeRequired(false);
    setCustomers([]);
    setSelectedCustomer(null);
    setHistory([]);
    setCustomerObjects([]);
    setDashboard(null);
    setInitialObjectId(null);
    setActiveModule("customers");
  }

  function selectModule(module: ActiveModule, fromSearch = false) {
    moduleSelectedManually.current = true;
    if (!fromSearch) setSearchResult(null);
    setActiveModule(module);
  }

  const clearInitialObjectId = useCallback(() => setInitialObjectId(null), []);

  async function openSearchResult(result: GlobalSearchResult) {
    setError("");
    if (result.type === "customer" && canReadCustomers) {
      selectModule("customers");
      try {
        await refreshSelected(result.id);
      } catch (reason) {
        setError(messageFrom(reason, "Kundendetails konnten nicht geladen werden."));
      }
    } else if (result.type === "object" && canReadObjects) {
      setInitialObjectId(result.id);
      selectModule("objects");
    } else {
      const moduleByType: Partial<Record<GlobalSearchResult["type"], ActiveModule>> = {
        employee: "employees",
        document: "documents",
        contract: "documents",
        shift: "scheduling",
        task: "tasks",
        incident: "incidents",
        key: "keys",
        inventory_asset: "inventory",
        owks_event: "owks",
      };
      const targetModule = moduleByType[result.type];
      if (targetModule) {
        setSearchResult(result);
        selectModule(targetModule, true);
      }
    }
  }

  async function signOut() {
    try {
      await logout();
    } finally {
      clearLocalSession();
    }
  }

  async function submitCustomer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    try {
      const payload = {
        company_name: String(data.get("company_name")).trim(),
        status: String(data.get("status")) as CustomerStatus,
        contract_status: String(data.get("contract_status")) as CustomerContractStatus,
        email: optionalValue(data, "email"),
        phone: optionalValue(data, "phone"),
        legal_form: optionalValue(data, "legal_form"),
        website: optionalValue(data, "website"),
        vat_number: optionalValue(data, "vat_number"),
        tax_number: optionalValue(data, "tax_number"),
        internal_notes: optionalValue(data, "internal_notes"),
        business_address: formAddress(data, "business"),
        billing_address: formAddress(data, "billing"),
      };
      const customer = await createCustomer(payload);
      form.reset();
      setOffset(0);
      await loadData();
      await refreshSelected(customer.id);
    } catch (reason) {
      setError(messageFrom(reason, "Kunde konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitCustomerUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCustomer) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    try {
      const payload = {
        company_name: String(data.get("company_name")).trim(),
        status: String(data.get("status")) as CustomerStatus,
        contract_status: String(data.get("contract_status")) as CustomerContractStatus,
        email: optionalValue(data, "email") ?? null,
        phone: optionalValue(data, "phone") ?? null,
        legal_form: optionalValue(data, "legal_form") ?? null,
        website: optionalValue(data, "website") ?? null,
        vat_number: optionalValue(data, "vat_number") ?? null,
        tax_number: optionalValue(data, "tax_number") ?? null,
        internal_notes: optionalValue(data, "internal_notes") ?? null,
        business_address: data.get("remove_business_address") === "on"
          ? null
          : formAddress(data, "edit_business"),
        billing_address: data.get("remove_billing_address") === "on"
          ? null
          : formAddress(data, "edit_billing"),
      };
      await updateCustomer(selectedCustomer.id, payload);
      await Promise.all([loadData(), refreshSelected(selectedCustomer.id)]);
    } catch (reason) {
      setError(messageFrom(reason, "Kundendaten konnten nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function changeStatus(customer: Customer, status: CustomerStatus) {
    try {
      await updateCustomer(customer.id, { status });
      await Promise.all([loadData(), selectedCustomer?.id === customer.id
        ? refreshSelected(customer.id)
        : Promise.resolve()]);
    } catch (reason) {
      setError(messageFrom(reason, "Status konnte nicht geändert werden."));
    }
  }

  async function changeArchiveState() {
    if (!selectedCustomer) return;
    const action = selectedCustomer.archived_at ? reactivateCustomer : archiveCustomer;
    setBusy(true);
    try {
      await action(selectedCustomer.id);
      await Promise.all([loadData(), refreshSelected(selectedCustomer.id)]);
    } catch (reason) {
      setError(messageFrom(reason, "Archivierungsstatus konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCustomer) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    try {
      await createCustomerContact(selectedCustomer.id, {
        first_name: String(data.get("first_name")).trim(),
        last_name: String(data.get("last_name")).trim(),
        responsibility: optionalValue(data, "responsibility"),
        email: optionalValue(data, "contact_email"),
        phone: optionalValue(data, "contact_phone"),
        is_primary: data.get("is_primary") === "on",
      });
      form.reset();
      await refreshSelected(selectedCustomer.id);
    } catch (reason) {
      setError(messageFrom(reason, "Ansprechpartner konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function updatePrimaryContact(customer: Customer, contactId: string, isPrimary: boolean) {
    try {
      await updateCustomerContact(customer.id, contactId, { is_primary: isPrimary });
      await refreshSelected(customer.id);
    } catch (reason) {
      setError(messageFrom(reason, "Ansprechpartner konnte nicht geändert werden."));
    }
  }

  async function removeContact(customer: Customer, contactId: string) {
    try {
      await deleteCustomerContact(customer.id, contactId);
      await refreshSelected(customer.id);
    } catch (reason) {
      setError(messageFrom(reason, "Ansprechpartner konnte nicht entfernt werden."));
    }
  }

  async function openCustomer(customer: Customer) {
    setError("");
    try {
      await refreshSelected(customer.id);
    } catch (reason) {
      setError(messageFrom(reason, "Kundendetails konnten nicht geladen werden."));
    }
  }

  if (authLoading) {
    return <main className="shell auth-shell"><p className="muted">Sitzung wird geprüft …</p></main>;
  }

  if (!user) {
    return (
      <main className="shell auth-shell">
        <header className="topbar">
          <a className="brand" href="/" aria-label="SecurityOps Startseite">
            <span className="brand-mark">S</span>
            <span>SECURITY<span className="brand-light">OPS</span></span>
          </a>
        </header>
        <section className="panel login-panel">
          <p className="eyebrow">SICHERER ZUGANG</p>
          <h1>Anmelden</h1>
          <p className="muted">Melde dich mit deinem SecurityOps-Konto an.</p>
          {error && <p className="alert" role="alert">{error}</p>}
          <form onSubmit={submitLogin}>
            <label>Benutzername
              <input name="username" required autoComplete="username" />
            </label>
            <label>Passwort
              <input name="password" type="password" required autoComplete="current-password" />
            </label>
            <label>MFA-Code oder Wiederherstellungscode (falls eingerichtet)
              <input name="mfa_factor" autoComplete="one-time-code" maxLength={32} />
            </label>
            <button type="submit" disabled={busy}>{busy ? "Anmeldung läuft …" : "Anmelden"}</button>
          </form>
        </section>
      </main>
    );
  }

  if (passwordChangeRequired) {
    return (
      <main className="shell auth-shell">
        <section className="panel login-panel">
          <p className="eyebrow">SICHERER ZUGANG</p>
          <h1>Passwort ändern</h1>
          <p className="muted">Das bereitgestellte Übergangspasswort muss vor der Nutzung geändert werden.</p>
          {error && <p className="alert" role="alert">{error}</p>}
          <form onSubmit={(event) => void submitRequiredPasswordChange(event)}>
            <label>Übergangspasswort
              <input name="current_password" type="password" autoComplete="current-password" required />
            </label>
            <label>Neues Passwort (mindestens 12 Zeichen)
              <input name="new_password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required />
            </label>
            <label>Neues Passwort wiederholen
              <input name="confirm_password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required />
            </label>
            <button type="submit" disabled={busy}>{busy ? "Passwort wird geändert …" : "Passwort ändern"}</button>
          </form>
        </section>
      </main>
    );
  }

  if (user.roles.includes("customer_portal")) {
    return <CustomerPortal user={user} onSignedOut={clearLocalSession} />;
  }

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="SecurityOps Startseite">
          <span className="brand-mark">S</span>
          <span>SECURITY<span className="brand-light">OPS</span></span>
        </a>
        <div className="account">
          <span className="topbar-label">{user.full_name}</span>
          <button className="sign-out" onClick={() => void signOut()}>Abmelden</button>
        </div>
      </header>

      <section className="intro">
        <p className="eyebrow">{isEmployeePortal ? "MITARBEITERPORTAL" : "SECURITYOPS VERWALTUNG"}</p>
        <h1>{isEmployeePortal ? `Guten Tag, ${user.full_name}.` : "Guten Tag."}</h1>
        <p>{isEmployeePortal
          ? "Eigene Dienste, Aufgaben, Qualifikationen, Arbeitszeiten und Anträge."
          : "Kunden, Objekte, Personal, Schlüssel, Inventar, Aufgaben, Dienste und Arbeitszeiten zentral verwalten."}</p>
      </section>

      <nav className="module-tabs" aria-label="Verwaltungsmodule">
        {isEmployeePortal ? <>
          <button
            className={activeModule === "employee_portal" ? "module-tab active" : "module-tab"}
            onClick={() => selectModule("employee_portal")}>Mitarbeiterportal</button>
          <button
            className={activeModule === "security" ? "module-tab active" : "module-tab"}
            onClick={() => selectModule("security")}>Sicherheit</button>
        </> : <>
        {(canReadCustomers || canCreateCustomers) && <button
          className={activeModule === "customers" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("customers")}>Kunden</button>}
        {user.permissions.includes("control_room.read") && <button
          className={activeModule === "control_room" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("control_room")}>Leitstelle</button>}
        {(canReadTasks || canCreateTasks) && <button
          className={activeModule === "tasks" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("tasks")}>Aufgaben</button>}
        {canReadNotifications && <button
          className={activeModule === "notifications" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("notifications")}>Benachrichtigungen</button>}
        {canManageAutomations && <button
          className={activeModule === "automations" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("automations")}>Automatisierungen</button>}
        {canReadObjects && <button
          className={activeModule === "objects" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("objects")}>Objekte</button>}
        {canReadKeys && <button
          className={activeModule === "keys" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("keys")}>Schlüssel</button>}
        {canReadInventory && <button
          className={activeModule === "inventory" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("inventory")}>Inventar</button>}
        {canReadEmployees && <button
          className={activeModule === "employees" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("employees")}>Personal</button>}
        {canReadScheduling && <button
          className={activeModule === "scheduling" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("scheduling")}>Dienstplanung</button>}
        {canReadTimeTracking && <button
          className={activeModule === "time_tracking" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("time_tracking")}>Zeiterfassung</button>}
        {canAccessDocuments && <button
          className={activeModule === "documents" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("documents")}>Dokumente & Verträge</button>}
        {canAccessBilling && <button
          className={activeModule === "billing" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("billing")}>Rechnungswesen</button>}
        {canReadOWKS && <button
          className={activeModule === "owks" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("owks")}>Wachbuch</button>}
        {canAccessIncidents && <button
          className={activeModule === "incidents" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("incidents")}>Vorfälle & Beschwerden</button>}
        {canManageCustomerPortal && <button
          className={activeModule === "customer_portal" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("customer_portal")}>Kundenportal</button>}
        <button
          className={activeModule === "security" ? "module-tab active" : "module-tab"}
          onClick={() => selectModule("security")}>Sicherheit</button>
        </>}
      </nav>

      {searchableTypes.length > 0 && (
        <GlobalSearch
          availableTypes={searchableTypes}
          onOpenResult={(result) => void openSearchResult(result)}
        />
      )}

      {activeModule === "security"
        ? <IdentitySecurity
          user={user}
          onSignedOut={clearLocalSession}
          onPasswordChanged={clearLocalSession}
        />
        : activeModule === "employee_portal" && isEmployeePortal
        ? <EmployeePortal />
        : activeModule === "customer_portal" && canManageCustomerPortal
        ? <CustomerPortalManagement
          canManageRequests={canManageCustomerPortalRequests}
          canManageDocuments={canManageCustomerPortalDocuments}
        />
        : activeModule === "tasks" && (canReadTasks || canCreateTasks)
        ? <TaskManagement
          user={user}
          initialTaskId={searchResult?.type === "task" ? searchResult.id : null}
        />
        : activeModule === "control_room" && user.permissions.includes("control_room.read")
        ? <ControlRoom />
        : activeModule === "keys" && canReadKeys
        ? <KeyManagement
          canManage={canManageKeys}
          canMove={canMoveKeys}
          initialQuery={searchResult?.type === "key" ? searchResult.reference : ""}
          initialKeyId={searchResult?.type === "key" ? searchResult.id : null}
        />
        : activeModule === "inventory" && canReadInventory
        ? <InventoryManagement
          canManage={canManageInventory}
          canManageGlobal={user.permissions.includes("objects.manage_all")}
          canMove={canMoveInventory}
          initialAssetId={searchResult?.type === "inventory_asset" ? searchResult.id : null}
          initialQuery={searchResult?.type === "inventory_asset" ? searchResult.reference : ""}
        />
        : activeModule === "notifications" && canReadNotifications
        ? <NotificationManagement />
        : activeModule === "automations" && canManageAutomations
        ? <AutomationManagement />
        : activeModule === "documents" && canAccessDocuments
        ? <DocumentContractManagement
          user={user}
          initialSearchResult={searchResult?.type === "document" || searchResult?.type === "contract"
            ? searchResult
            : null}
        />
        : activeModule === "billing" && canAccessBilling
        ? <BillingManagement user={user} />
        : activeModule === "owks" && canReadOWKS
        ? <OWKSManagement
          user={user}
          initialEventId={searchResult?.type === "owks_event" ? searchResult.id : null}
        />
        : activeModule === "incidents" && canAccessIncidents
        ? <IncidentManagement
          user={user}
          initialIncidentId={searchResult?.type === "incident" ? searchResult.id : null}
        />
        : activeModule === "time_tracking" && canReadTimeTracking
        ? <TimeTracking user={user} />
        : activeModule === "scheduling" && canReadScheduling
        ? <SchedulingManagement
          user={user}
          initialShiftDate={searchResult?.type === "shift" ? searchResult.reference.slice(0, 10) : undefined}
          initialShiftId={searchResult?.type === "shift" ? searchResult.id : null}
        />
        : activeModule === "employees" && canReadEmployees
        ? <PersonnelManagement
          user={user}
          initialSearch={searchResult?.type === "employee" ? searchResult.reference : ""}
          initialEmployeeId={searchResult?.type === "employee" ? searchResult.id : null}
        />
        : activeModule === "objects" && canReadObjects ? (
          <ObjectManagement
            user={user}
            initialObjectId={initialObjectId}
            onInitialObjectOpened={clearInitialObjectId}
          />
        ) : <>
      {dashboard && <section className="stats" aria-label="Kundenübersicht">
        <article className="stat-card"><span>Kunden gesamt</span><strong>{dashboard.customers_total}</strong></article>
        <article className="stat-card"><span>Aktive Kunden</span><strong>{dashboard.customers_active}</strong></article>
        <article className="stat-card"><span>Interessenten</span><strong>{dashboard.customers_leads}</strong></article>
      </section>}

      {error && <p className="alert page-alert" role="alert">{error}</p>}

      <section className="content-grid">
        {canReadCustomers && <section className="panel">
          <div className="panel-heading">
            <div><p className="eyebrow">STAMMDATEN</p><h2>Kunden</h2></div>
            <span className="result-count">{matchingCustomers} Einträge</span>
          </div>
          <label className="search-field">
            <span className="sr-only">Kunden suchen</span>
            <span aria-hidden="true">⌕</span>
            <input
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setOffset(0);
              }}
              placeholder="Name, Nummer, Kontakt oder Ort suchen"
            />
          </label>
          <div className="filter-row">
            <label>Status
              <select value={statusFilter} onChange={(event) => {
                setStatusFilter(event.target.value as CustomerStatus | "");
                setOffset(0);
              }}>
                <option value="">Alle Status</option>
                {Object.entries(statusNames).map(([value, name]) =>
                  <option key={value} value={value}>{name}</option>,
                )}
              </select>
            </label>
            <label>Vertragsstatus
              <select value={contractStatusFilter} onChange={(event) => {
                setContractStatusFilter(event.target.value as CustomerContractStatus | "");
                setOffset(0);
              }}>
                <option value="">Alle Vertragsstatus</option>
                {Object.entries(contractStatusNames).map(([value, name]) =>
                  <option key={value} value={value}>{name}</option>,
                )}
              </select>
            </label>
            <label>Sortieren nach
              <select value={sortBy} onChange={(event) => setSortBy(event.target.value as CustomerSort)}>
                <option value="company_name">Unternehmen</option>
                <option value="customer_number">Kundennummer</option>
                <option value="created_at">Angelegt am</option>
                <option value="status">Status</option>
                <option value="contract_status">Vertragsstatus</option>
              </select>
            </label>
            <label>Reihenfolge
              <select value={sortOrder} onChange={(event) => setSortOrder(event.target.value as "asc" | "desc")}>
                <option value="asc">Aufsteigend</option>
                <option value="desc">Absteigend</option>
              </select>
            </label>
            {canArchiveCustomers && <label className="checkbox-label">
              <input type="checkbox" checked={includeArchived} onChange={(event) => {
                setIncludeArchived(event.target.checked);
                setOffset(0);
              }} />
              Archivierte einblenden
            </label>}
          </div>
          <div className="table-scroll">
            <table>
              <thead><tr><th>Kunde</th><th>Kontakt</th><th>Status</th><th>Details</th></tr></thead>
              <tbody>
                {customers.map((customer) => {
                  const primary = customer.contacts.find((contact) => contact.is_primary);
                  return (
                    <tr key={customer.id} className={customer.archived_at ? "archived-row" : ""}>
                      <td><strong>{customer.company_name}</strong><small>{customer.customer_number}</small></td>
                      <td>
                        {primary
                          ? <><strong>{primary.first_name} {primary.last_name}</strong>
                            {primary.email && <small><a href={`mailto:${primary.email}`}>{primary.email}</a></small>}</>
                          : <>{customer.email && <a href={`mailto:${customer.email}`}>{customer.email}</a>}
                            {customer.phone && <small>{customer.phone}</small>}
                            {!customer.email && !customer.phone && <span className="muted">Keine Kontaktdaten</span>}</>}
                      </td>
                      <td>
                        {canUpdateCustomers && !customer.archived_at ? (
                          <label className="sr-only" htmlFor={`status-${customer.id}`}>Status für {customer.company_name}</label>
                        ) : null}
                        {canUpdateCustomers && !customer.archived_at ? (
                          <select id={`status-${customer.id}`} value={customer.status}
                            onChange={(event) => void changeStatus(customer, event.target.value as CustomerStatus)}>
                            {Object.entries(statusNames).map(([value, name]) =>
                              <option key={value} value={value}>{name}</option>,
                            )}
                          </select>
                        ) : <span className={`status status-${customer.status}`}>
                          {customer.archived_at ? "Archiviert" : statusNames[customer.status]}
                        </span>}
                      </td>
                      <td><button className="text-button" onClick={() => void openCustomer(customer)}>Öffnen</button></td>
                    </tr>
                  );
                })}
                {customers.length === 0 && (
                  <tr><td className="empty" colSpan={4}>Keine passenden Kunden vorhanden.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <span className="result-count">{matchingCustomers === 0 ? 0 : offset + 1}–{Math.min(offset + pageSize, matchingCustomers)} von {matchingCustomers}</span>
            <div>
              <button className="secondary-button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Zurück</button>
              <button className="secondary-button" disabled={offset + pageSize >= matchingCustomers}
                onClick={() => setOffset(offset + pageSize)}>Weiter</button>
            </div>
          </div>
        </section>}

        {canCreateCustomers && <aside className="panel form-panel">
          <div className="panel-heading"><div><p className="eyebrow">NEU ANLEGEN</p><h2>Kunde hinzufügen</h2></div></div>
          <form onSubmit={submitCustomer}>
            <label>Unternehmen <span aria-hidden="true">*</span>
              <input name="company_name" required maxLength={200} placeholder="Muster GmbH" />
            </label>
            <label>Status
              <select name="status" defaultValue="active">
                {Object.entries(statusNames).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
              </select>
            </label>
            <label>Vertragsstatus
              <select name="contract_status" defaultValue="none">
                {Object.entries(contractStatusNames).map(([value, name]) =>
                  <option key={value} value={value}>{name}</option>,
                )}
              </select>
            </label>
            <label>E-Mail<input name="email" type="email" maxLength={254} /></label>
            <label>Telefon<input name="phone" type="tel" maxLength={40} /></label>
            <label>Rechtsform<input name="legal_form" maxLength={100} placeholder="GmbH, e.K. …" /></label>
            <label>Website<input name="website" type="url" maxLength={2048} placeholder="https://beispiel.de" /></label>
            <label>Umsatzsteuer-ID<input name="vat_number" maxLength={32} /></label>
            <label>Steuernummer<input name="tax_number" maxLength={32} /></label>
            <AddressFields prefix="business" title="Geschäftsanschrift" />
            <AddressFields prefix="billing" title="Rechnungsanschrift (optional)" />
            <label>Interne Notizen<textarea name="internal_notes" maxLength={10000} rows={3} /></label>
            <button type="submit" disabled={busy}>{busy ? "Wird gespeichert …" : "Kunden speichern"}</button>
          </form>
        </aside>}
        {!canReadCustomers && !canCreateCustomers && (
          <section className="panel"><h2>Kein Modulzugriff</h2><p className="muted">Deinem Konto sind aktuell keine Kundenverwaltungsrechte zugewiesen.</p></section>
        )}
      </section>

      {selectedCustomer && canReadCustomers && <section className="panel detail-panel" aria-labelledby="customer-detail-title">
        <div className="panel-heading">
          <div><p className="eyebrow">KUNDENDETAILS · {selectedCustomer.customer_number}</p>
            <h2 id="customer-detail-title">{selectedCustomer.company_name}</h2></div>
          <button className="secondary-button" onClick={() => {
            setSelectedCustomer(null);
            setHistory([]);
          }}>Schließen</button>
        </div>
        <div className="detail-grid">
          {canUpdateCustomers && !selectedCustomer.archived_at ? <form className="form-panel detail-form" onSubmit={submitCustomerUpdate}>
            <label>Unternehmen<input name="company_name" required maxLength={200} defaultValue={selectedCustomer.company_name} /></label>
            <label>Status<select name="status" defaultValue={selectedCustomer.status}>
              {Object.entries(statusNames).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
            </select></label>
            <label>Vertragsstatus<select name="contract_status" defaultValue={selectedCustomer.contract_status}>
              {Object.entries(contractStatusNames).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
            </select></label>
            <label>E-Mail<input name="email" type="email" maxLength={254} defaultValue={selectedCustomer.email ?? ""} /></label>
            <label>Telefon<input name="phone" maxLength={40} defaultValue={selectedCustomer.phone ?? ""} /></label>
            <label>Rechtsform<input name="legal_form" maxLength={100} defaultValue={selectedCustomer.legal_form ?? ""} /></label>
            <label>Website<input name="website" type="url" maxLength={2048} defaultValue={selectedCustomer.website ?? ""} /></label>
            <label>Umsatzsteuer-ID<input name="vat_number" maxLength={32} defaultValue={selectedCustomer.vat_number ?? ""} /></label>
            <label>Steuernummer<input name="tax_number" maxLength={32} defaultValue={selectedCustomer.tax_number ?? ""} /></label>
            <AddressFields prefix="edit_business" title="Geschäftsanschrift" address={selectedCustomer.business_address} />
            {selectedCustomer.business_address && <label className="checkbox-label">
              <input type="checkbox" name="remove_business_address" /> Geschäftsanschrift entfernen
            </label>}
            <AddressFields prefix="edit_billing" title="Rechnungsanschrift" address={selectedCustomer.billing_address} />
            {selectedCustomer.billing_address && <label className="checkbox-label">
              <input type="checkbox" name="remove_billing_address" /> Rechnungsanschrift entfernen
            </label>}
            <label>Interne Notizen<textarea name="internal_notes" maxLength={10000} rows={3}
              defaultValue={selectedCustomer.internal_notes ?? ""} /></label>
            <button type="submit" disabled={busy}>Änderungen speichern</button>
          </form> : <div className="detail-summary">
            <p><strong>Status:</strong> {selectedCustomer.archived_at ? "Archiviert" : statusNames[selectedCustomer.status]}</p>
            <p><strong>Vertragsstatus:</strong> {contractStatusNames[selectedCustomer.contract_status]}</p>
            {selectedCustomer.legal_form && <p><strong>Rechtsform:</strong> {selectedCustomer.legal_form}</p>}
            {selectedCustomer.website && <p><strong>Website:</strong> <a href={selectedCustomer.website} target="_blank" rel="noreferrer">{selectedCustomer.website}</a></p>}
            {selectedCustomer.vat_number && <p><strong>USt-IdNr.:</strong> {selectedCustomer.vat_number}</p>}
            {selectedCustomer.tax_number && <p><strong>Steuernummer:</strong> {selectedCustomer.tax_number}</p>}
            {selectedCustomer.internal_notes && <p><strong>Interne Notizen:</strong><br />{selectedCustomer.internal_notes}</p>}
            <AddressSummary title="Geschäftsanschrift" address={selectedCustomer.business_address} />
            <AddressSummary title="Rechnungsanschrift" address={selectedCustomer.billing_address} />
          </div>}

          <div className="detail-side">
            {canArchiveCustomers && <div className="archive-box">
              <h3>{selectedCustomer.archived_at ? "Archivierter Kunde" : "Kundenstatus"}</h3>
              <p className="muted">{selectedCustomer.archived_at
                ? `Archiviert am ${new Date(selectedCustomer.archived_at).toLocaleString("de-DE")}.`
                : "Archivierte Kunden werden standardmäßig aus der Liste und den Kennzahlen ausgeblendet."}</p>
              <button className={selectedCustomer.archived_at ? "primary-button" : "danger-button"}
                disabled={busy} onClick={() => void changeArchiveState()}>
                {selectedCustomer.archived_at ? "Reaktivieren" : "Kunde archivieren"}
              </button>
            </div>}
            <section className="contact-section">
              <h3>Ansprechpartner</h3>
              {selectedCustomer.contacts.length === 0 && <p className="muted">Noch keine Ansprechpartner hinterlegt.</p>}
              {selectedCustomer.contacts.map((contact) => (
                <article className="contact-card" key={contact.id}>
                  <div><strong>{contact.first_name} {contact.last_name}</strong>
                    {contact.is_primary && <span className="primary-tag">Primär</span>}
                    {contact.responsibility && <small>{contact.responsibility}</small>}
                    {contact.email && <small><a href={`mailto:${contact.email}`}>{contact.email}</a></small>}
                    {contact.phone && <small>{contact.phone}</small>}
                  </div>
                  {canUpdateCustomers && !selectedCustomer.archived_at && <div className="contact-actions">
                    {!contact.is_primary && <button className="text-button" onClick={() => void updatePrimaryContact(selectedCustomer, contact.id, true)}>Als primär setzen</button>}
                    <button className="text-button danger-text" onClick={() => void removeContact(selectedCustomer, contact.id)}>Entfernen</button>
                  </div>}
                </article>
              ))}
              {canUpdateCustomers && !selectedCustomer.archived_at && <form className="contact-form" onSubmit={submitContact}>
                <h4>Ansprechpartner hinzufügen</h4>
                <div className="form-row">
                  <label>Vorname<input name="first_name" required maxLength={100} /></label>
                  <label>Nachname<input name="last_name" required maxLength={100} /></label>
                </div>
                <label>Funktion<input name="responsibility" maxLength={120} /></label>
                <label>E-Mail<input name="contact_email" type="email" maxLength={254} /></label>
                <label>Telefon<input name="contact_phone" maxLength={40} /></label>
                <label className="checkbox-label"><input type="checkbox" name="is_primary" /> Primärer Ansprechpartner</label>
                <button className="secondary-button" type="submit" disabled={busy}>Hinzufügen</button>
              </form>}
            </section>
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
      {selectedCustomer && canReadObjects && <section className="panel related-objects" aria-labelledby="related-objects-title">
        <h3 id="related-objects-title">Zugeordnete Objekte</h3>
        {customerObjects.length === 0
          ? <p className="muted">Keine erreichbaren Objekte zugeordnet.</p>
          : <ul className="related-object-list">{customerObjects.map((object) => (
            <li key={object.id}>
              <span><strong>{object.name}</strong><small>{object.code}</small></span>
              <span className={object.archived_at ? "muted" : `status status-${object.status}`}>
                {object.archived_at ? "Archiviert" : objectStatusNames[object.status]}
              </span>
            </li>
          ))}</ul>}
      </section>}
      </>}
      <footer>SecurityOps <span>·</span> Verwaltung</footer>
    </main>
  );
}

function AddressSummary({ title, address }: { title: string; address: CustomerAddress | null }) {
  if (!address) return null;
  return <p><strong>{title}:</strong><br />{address.street} {address.house_number}<br />
    {address.postal_code} {address.city}<br />{address.country_code}</p>;
}
