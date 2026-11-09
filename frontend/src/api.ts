import type {
  AuthUser,
  Customer,
  CustomerAddressInput,
  CustomerContractStatus,
  CustomerContact,
  CustomerContactInput,
  CustomerHistory,
  CustomerPage,
  CustomerSort,
  CustomerStatus,
  Dashboard,
  Employee,
  EmployeeAccountCandidate,
  EmployeeAbsence,
  EmployeeAbsenceStatus,
  EmployeeAbsenceType,
  EmployeePortalAbsence,
  EmployeePortalAvailabilityRequest,
  EmployeePortalNotification,
  EmployeePortalProfile,
  EmployeePortalQualification,
  EmployeePortalShift,
  EmployeePortalTask,
  EmployeePortalTimeOverview,
  EmployeeAvailabilityWindow,
  EmployeeHistory,
  EmployeeObjectAssignment,
  EmployeeObjectAssignmentHistory,
  EmployeeObjectCandidate,
  EmployeePage,
  EmployeeQualification,
  EmployeeQualificationDocument,
  EmployeeSensitiveDetails,
  EmployeeStatus,
  ObjectAddressInput,
  ObjectAssignment,
  ObjectAssignmentCandidate,
  ObjectContact,
  ObjectContactInput,
  ObjectHistory,
  ObjectPage,
  ObjectSecurityDetails,
  ObjectSort,
  ObjectStatus,
  SecurityObject,
  Session,
  UserSession,
  MFASetup,
  MFAStatus,
  ScheduleSettings,
  ScheduleAvailabilityRequest,
  ScheduleAvailabilityRequestKind,
  ScheduleReplacementReason,
  ScheduleShift,
  ScheduleShiftHistory,
  ScheduleReplacementCandidate,
  TimeEntry,
  TimeEntryCorrection,
  TimeEntrySummary,
  MissingShift,
  NotificationItem,
  NotificationPage,
  FederalState,
  TimeSurchargeCalculation,
  TimeSurchargeCategory,
  TimeSurchargeRule,
  TimeTrackingPeriod,
  ContractPage,
  ContractStatus,
  ContractType,
  DocumentPage,
  DocumentApproval,
  DocumentApprovalQueueItem,
  DocumentReadReceipt,
  DocumentVersion,
  ManagedContract,
  ManagedDocument,
  ManagedReminder,
  ReminderSettings,
  OWKSObject,
  OWKSControlPoint,
  OWKSRoute,
  OWKSEvent,
  OWKSSyncResult,
  OWKSAttachment,
  BillingRate,
  BillingInvoice,
  TaskAssignee,
  TaskDetail,
  TaskItem,
  TaskLocations,
  TaskPage,
  TaskPriority,
  TaskStatus,
  PhysicalKey,
  PhysicalKeyPage,
  PhysicalKeyStatus,
  KeyMovement,
  KeyMovementPage,
  KeyMovementType,
  KeyEmployeeCandidate,
  KeyObjectCandidate,
  InventoryActionType,
  InventoryAsset,
  InventoryAssetPage,
  InventoryCategory,
  InventoryCondition,
  InventoryEmployeeCandidate,
  InventoryEvent,
  InventoryEventPage,
  InventoryObjectCandidate,
  InventoryStatus,
  IncidentDetail,
  IncidentItem,
  IncidentPage,
  IncidentChoices,
  IncidentPerson,
  IncidentAttachment,
  IncidentSensitiveDetails,
  IncidentStatus,
  IncidentType,
  IncidentSeverity,
  IncidentMeasure,
  ControlRoom,
  CustomerPortalInvoice,
  CustomerPortalMe,
  CustomerPortalDocument,
  CustomerPortalLink,
  CustomerPortalManagementOptions,
  CustomerPortalLinkHistory,
  CustomerPortalAccessEvent,
  CustomerPortalDocumentCandidate,
  CustomerPortalDocumentGrant,
  CustomerPortalRequest,
  CustomerPortalRequestMessage,
  CustomerPortalRequestAttachment,
  GlobalSearchEntityType,
  GlobalSearchPage,
  AutomationRule,
  AutomationTrigger,
  AutomationTaskStatus,
  AutomationRunPage,
  AutomationDeadLetterPage,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method?.toUpperCase() ?? "GET";
  const isFormData = init?.body instanceof FormData;
  const csrf = method === "GET" || method === "HEAD"
    ? undefined
    : document.cookie.split("; ").find((cookie) => cookie.startsWith("securityops_csrf="))?.split("=")[1];
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    credentials: "same-origin",
    headers: {
      ...(!isFormData ? { "Content-Type": "application/json" } : {}),
      ...(csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {}),
      ...init?.headers,
    },
  });
  if (response.status === 204) return undefined as T;
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const validationError = Array.isArray(detail);
    const conflicts = Array.isArray(detail?.conflicts)
      ? detail.conflicts
        .map((conflict: { message?: unknown }) =>
          typeof conflict.message === "string" ? conflict.message : "",
        )
        .filter(Boolean)
      : [];
    throw new Error(
      typeof detail === "string"
        ? detail
        : validationError
          ? "Eingaben sind ungültig. Bitte Eingaben prüfen."
        : typeof detail?.message === "string"
          ? [detail.message, ...conflicts].join(" ")
          : `Serverfehler (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}

export const getSession = () => request<Session>("/auth/me");

export const getCustomerPortalMe = () => request<CustomerPortalMe>("/customer-portal/me");

export const getCustomerPortalInvoices = () =>
  request<CustomerPortalInvoice[]>("/customer-portal/invoices");

export const getCustomerPortalDocuments = () =>
  request<CustomerPortalDocument[]>("/customer-portal/documents");

export const getCustomerPortalLinks = () =>
  request<CustomerPortalLink[]>("/customer-portal/links");

export const getCustomerPortalManagementOptions = () =>
  request<CustomerPortalManagementOptions>("/customer-portal/management-options");

export const getCustomerPortalLinkHistory = () =>
  request<CustomerPortalLinkHistory[]>("/customer-portal/link-history");

export const getCustomerPortalAccessHistory = () =>
  request<CustomerPortalAccessEvent[]>("/customer-portal/access-history");

export const createCustomerPortalLink = (user_id: string, contact_id: string) =>
  request<CustomerPortalLink>("/customer-portal/links", {
    method: "POST",
    body: JSON.stringify({ user_id, contact_id }),
  });

export const setCustomerPortalLinkActive = (contactId: string, is_active: boolean) =>
  request<CustomerPortalLink>(`/customer-portal/links/${encodeURIComponent(contactId)}`, {
    method: "PATCH",
    body: JSON.stringify({ is_active }),
  });

export const unlinkCustomerPortalContact = (contactId: string) =>
  request<void>(`/customer-portal/links/${encodeURIComponent(contactId)}`, {
    method: "DELETE",
  });

export const getCustomerPortalDocumentCandidates = () =>
  request<CustomerPortalDocumentCandidate[]>("/customer-portal/document-candidates");

export const getCustomerPortalDocumentGrants = (documentId: string) =>
  request<CustomerPortalDocumentGrant[]>(
    `/customer-portal/document-grants?document_id=${encodeURIComponent(documentId)}`,
  );

export const grantCustomerPortalDocument = (document_id: string, version_id: string) =>
  request<CustomerPortalDocumentGrant>("/customer-portal/document-grants", {
    method: "POST",
    body: JSON.stringify({ document_id, version_id }),
  });

export const revokeCustomerPortalDocument = (grantId: string) =>
  request<CustomerPortalDocumentGrant>(
    `/customer-portal/document-grants/${encodeURIComponent(grantId)}`,
    { method: "DELETE" },
  );

export const getCustomerPortalRequests = () =>
  request<CustomerPortalRequest[]>("/customer-portal/requests");

export const createCustomerPortalRequest = (payload: {
  category: "request" | "question" | "complaint";
  object_id: string;
  title: string;
  first_message: string;
}) =>
  request<CustomerPortalRequest>("/customer-portal/requests", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const addCustomerPortalRequestMessage = (requestId: string, body: string) =>
  request<CustomerPortalRequestMessage>(
    `/customer-portal/requests/${encodeURIComponent(requestId)}/messages`,
    { method: "POST", body: JSON.stringify({ body }) },
  );

export async function uploadCustomerPortalRequestAttachment(
  requestId: string,
  file: File,
): Promise<CustomerPortalRequestAttachment> {
  const form = new FormData();
  form.append("file", file);
  return request<CustomerPortalRequestAttachment>(
    `/customer-portal/requests/${encodeURIComponent(requestId)}/attachments`,
    { method: "POST", body: form },
  );
}

export async function downloadCustomerPortalRequestAttachment(
  requestId: string,
  attachmentId: string,
): Promise<Blob> {
  const response = await fetch(
    `/api/v1/customer-portal/requests/${encodeURIComponent(requestId)}/attachments/${encodeURIComponent(attachmentId)}/download`,
    { credentials: "same-origin" },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : `Serverfehler (${response.status})`,
    );
  }
  return response.blob();
}

export const getManagedCustomerPortalRequests = () =>
  request<CustomerPortalRequest[]>("/customer-portal/admin/requests");

export const addManagedCustomerPortalRequestMessage = (requestId: string, body: string) =>
  request<CustomerPortalRequestMessage>(
    `/customer-portal/admin/requests/${encodeURIComponent(requestId)}/messages`,
    { method: "POST", body: JSON.stringify({ body }) },
  );

export const updateManagedCustomerPortalRequestStatus = (
  requestId: string,
  status: CustomerPortalRequest["status"],
) =>
  request<CustomerPortalRequest>(
    `/customer-portal/admin/requests/${encodeURIComponent(requestId)}/status`,
    { method: "PATCH", body: JSON.stringify({ status }) },
  );

export async function downloadManagedCustomerPortalRequestAttachment(
  requestId: string,
  attachmentId: string,
): Promise<Blob> {
  const response = await fetch(
    `/api/v1/customer-portal/admin/requests/${encodeURIComponent(requestId)}/attachments/${encodeURIComponent(attachmentId)}/download`,
    { credentials: "same-origin" },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : `Serverfehler (${response.status})`,
    );
  }
  return response.blob();
}

export async function downloadCustomerPortalDocument(grantId: string): Promise<Blob> {
  const response = await fetch(
    `/api/v1/customer-portal/documents/${encodeURIComponent(grantId)}/download`,
    { credentials: "same-origin" },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : `Serverfehler (${response.status})`,
    );
  }
  return response.blob();
}

export async function downloadCustomerPortalInvoice(invoiceId: string): Promise<Blob> {
  const response = await fetch(
    `/api/v1/customer-portal/invoices/${encodeURIComponent(invoiceId)}/pdf`,
    { credentials: "same-origin" },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : `Serverfehler (${response.status})`,
    );
  }
  return response.blob();
}

export const getControlRoom = (filters: {
  object_id?: string;
  from_date?: string;
  to_date?: string;
}) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  return request<ControlRoom>(`/control-room?${params.toString()}`);
};

export const getGlobalSearch = (filters: {
  q: string;
  type?: GlobalSearchEntityType | "";
  limit?: number;
  offset?: number;
}) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  return request<GlobalSearchPage>(`/search?${params.toString()}`);
};

export const getNotifications = (filters: {
  limit?: number;
  offset?: number;
  unread_only?: boolean;
}) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined) params.set(key, String(value));
  }
  return request<NotificationPage>(`/notifications?${params.toString()}`);
};

export const markNotificationRead = (notificationId: string) =>
  request<NotificationItem>(`/notifications/${notificationId}/read`, { method: "PATCH" });

export const getAutomationRules = () => request<AutomationRule[]>("/automations/rules");

export const createAutomationRule = (data: {
  name: string;
  description?: string;
  trigger_type: AutomationTrigger;
  conditions: { status?: AutomationTaskStatus };
}) => request<AutomationRule>("/automations/rules", {
  method: "POST",
  body: JSON.stringify({ ...data, action_type: "notify_event_recipients" }),
});

export const updateAutomationRule = (
  ruleId: string,
  data: Partial<Pick<AutomationRule, "name" | "description" | "trigger_type" | "conditions" | "is_active">>,
) => request<AutomationRule>(`/automations/rules/${ruleId}`, {
  method: "PATCH",
  body: JSON.stringify(data),
});

export const deleteAutomationRule = (ruleId: string) =>
  request<void>(`/automations/rules/${ruleId}`, { method: "DELETE" });

export const getAutomationRuns = (filters: { limit?: number; offset?: number } = {}) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined) params.set(key, String(value));
  }
  return request<AutomationRunPage>(`/automations/runs?${params.toString()}`);
};

export const getAutomationDeadLetters = (limit = 25) =>
  request<AutomationDeadLetterPage>(`/automations/outbox-events?limit=${limit}`);

export const retryAutomationRun = (runId: string) =>
  request<{ status: string }>(`/automations/runs/${runId}/retry`, { method: "POST" });

export const retryAutomationEvent = (eventId: string) =>
  request<{ status: string }>(`/automations/outbox-events/${eventId}/retry`, { method: "POST" });

export const getIncidents = (filters: {
  status?: IncidentStatus | "";
  object_id?: string;
  overdue?: boolean;
  limit?: number;
  offset?: number;
}) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  return request<IncidentPage>(`/incidents?${params.toString()}`);
};

export const getIncident = (incidentId: string) =>
  request<IncidentDetail>(`/incidents/${incidentId}`);

export const getIncidentChoices = (objectId?: string) => {
  const query = objectId ? `?object_id=${encodeURIComponent(objectId)}` : "";
  return request<IncidentChoices>(`/incidents/choices${query}`);
};

export const createIncident = (data: {
  title: string;
  report: string;
  incident_type: IncidentType;
  severity: IncidentSeverity;
  object_id: string;
  due_at?: string;
  assigned_to_id?: string;
  owks_event_id?: string;
}) => request<IncidentItem>("/incidents", { method: "POST", body: JSON.stringify(data) });

export const updateIncident = (
  incidentId: string,
  data: Partial<Pick<IncidentItem, "title" | "report" | "incident_type" | "severity" | "due_at" | "assigned_to_id">>,
) => request<IncidentItem>(`/incidents/${incidentId}`, {
  method: "PATCH",
  body: JSON.stringify(data),
});

export const updateIncidentStatus = (incidentId: string, status: IncidentStatus) =>
  request<IncidentItem>(`/incidents/${incidentId}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });

export const updateIncidentSensitiveDetails = (
  incidentId: string,
  data: Pick<IncidentSensitiveDetails, "narrative" | "closure_report">,
) => request<IncidentSensitiveDetails>(`/incidents/${incidentId}/sensitive`, {
  method: "PATCH",
  body: JSON.stringify(data),
});

export const addIncidentPerson = (
  incidentId: string,
  data: Pick<IncidentPerson, "name" | "role" | "notes">,
) => request<IncidentPerson>(`/incidents/${incidentId}/people`, {
  method: "POST",
  body: JSON.stringify(data),
});

export const createIncidentMeasure = (
  incidentId: string,
  data: {
    title: string;
    description?: string;
    due_at?: string;
    assigned_to_id: string;
  },
) => request<IncidentMeasure>(`/incidents/${incidentId}/measures`, {
  method: "POST",
  body: JSON.stringify(data),
});

export const updateIncidentMeasure = (
  incidentId: string,
  measureId: string,
  data: Partial<Pick<IncidentMeasure, "title" | "description" | "due_at" | "assigned_to_id" | "status">>,
) => request<IncidentMeasure>(`/incidents/${incidentId}/measures/${measureId}`, {
  method: "PATCH",
  body: JSON.stringify(data),
});

export const uploadIncidentAttachment = (incidentId: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return request<IncidentAttachment>(`/incidents/${incidentId}/attachments`, {
    method: "POST",
    body: form,
  });
};

export const downloadIncidentAttachment = async (incidentId: string, attachmentId: string) => {
  const csrf = document.cookie.split("; ").find((cookie) =>
    cookie.startsWith("securityops_csrf="))?.split("=")[1];
  const response = await fetch(
    `/api/v1/incidents/${incidentId}/attachments/${attachmentId}/download`,
    {
      credentials: "same-origin",
      headers: csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {},
    },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Serverfehler (${response.status})`);
  }
  return response.blob();
};

export interface TaskFilters {
  q?: string;
  status?: TaskStatus | "";
  priority?: TaskPriority | "";
  overdue?: boolean;
  limit?: number;
  offset?: number;
}

export const getTasks = (filters: TaskFilters) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  return request<TaskPage>(`/tasks?${params.toString()}`);
};

export const getTask = (taskId: string) => request<TaskDetail>(`/tasks/${taskId}`);

export const getTaskLocations = () => request<TaskLocations>("/tasks/locations");

export const getTaskAssignees = (objectId?: string) => {
  const query = objectId ? `?object_id=${encodeURIComponent(objectId)}` : "";
  return request<TaskAssignee[]>(`/tasks/assignees${query}`);
};

export const createTask = (data: {
  title: string;
  description?: string;
  assigned_to_id?: string;
  customer_id?: string;
  object_id?: string;
  due_at?: string;
  priority: TaskPriority;
}) => request<TaskItem>("/tasks", { method: "POST", body: JSON.stringify(data) });

export const updateTask = (
  taskId: string,
  data: Partial<Pick<TaskItem, "title" | "description" | "assigned_to_id" | "customer_id"
    | "object_id" | "due_at" | "priority" | "status" | "completion_evidence">>,
) => request<TaskItem>(`/tasks/${taskId}`, { method: "PATCH", body: JSON.stringify(data) });

export const createTaskComment = (taskId: string, body: string) =>
  request<TaskDetail["comments"][number]>(`/tasks/${taskId}/comments`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });

export const getBillingRates = () => request<BillingRate[]>("/billing/rates");

export const getBillingInvoices = () => request<BillingInvoice[]>("/billing/invoices");

export const createBillingRate = (data: {
  code: string;
  name: string;
  kind: "hourly" | "flat" | "surcharge";
  unit: string;
  unit_price: string;
  tax_code: string;
  tax_rate: string;
  currency: string;
}) => request<BillingRate>("/billing/rates", { method: "POST", body: JSON.stringify(data) });

export const createBillingInvoice = (data: {
  idempotency_key: string;
  customer_id: string;
  issued_on: string;
  due_on: string;
  lines: Array<{ rate_id: string; quantity: string }>;
}) => request<BillingInvoice>("/billing/invoices", { method: "POST", body: JSON.stringify(data) });

export const approveBillingInvoice = (id: string) =>
  request<BillingInvoice>(`/billing/invoices/${id}/approve`, { method: "POST" });

export const archiveBillingInvoice = (id: string, reason: string) =>
  request<BillingInvoice>(`/billing/invoices/${id}/archive`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

export const createBillingCorrection = (id: string, reason: string, idempotency_key: string) =>
  request<BillingInvoice>(`/billing/invoices/${id}/corrections`, {
    method: "POST",
    body: JSON.stringify({
      idempotency_key,
      reason,
      issued_on: new Date().toISOString().slice(0, 10),
      due_on: new Date().toISOString().slice(0, 10),
    }),
  });

export const exportBillingInvoice = (id: string, idempotencyKey: string) =>
  request<{ payload: object; payload_sha256: string }>(
    `/billing/invoices/${id}/exports?idempotency_key=${encodeURIComponent(idempotencyKey)}`,
    { method: "POST" },
  );

export const addBillingPayment = (id: string, amount: string) =>
  request(`/billing/invoices/${id}/payments`, {
    method: "POST",
    body: JSON.stringify({
      idempotency_key: crypto.randomUUID(),
      amount,
      paid_on: new Date().toISOString().slice(0, 10),
    }),
  });

export const updateBillingDunning = (
  id: string,
  status: "none" | "reminder_1" | "reminder_2" | "final",
  note: string,
) => request<BillingInvoice>(`/billing/invoices/${id}/dunning`, {
  method: "PATCH",
  body: JSON.stringify({ status, note }),
});

export const login = (
  username: string,
  password: string,
  factor?: { mfa_code: string } | { recovery_code: string },
) =>
  request<Session>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password, ...factor }),
  });

export const logout = () => request<void>("/auth/logout", { method: "POST" });

export const getUserSessions = () => request<UserSession[]>("/auth/sessions");

export const getUserSessionsForAdmin = (userId: string) =>
  request<UserSession[]>(`/users/${userId}/sessions`);

export const revokeUserSession = (id: string) =>
  request<void>(`/auth/sessions/${id}`, { method: "DELETE" });

export const getMFAStatus = () => request<MFAStatus>("/auth/mfa");

export const startMFASetup = (current_password: string) =>
  request<MFASetup>("/auth/mfa/setup", {
    method: "POST",
    body: JSON.stringify({ current_password }),
  });

export const enableMFA = (code: string) =>
  request<{ recovery_codes: string[] }>("/auth/mfa/enable", {
    method: "POST",
    body: JSON.stringify({ code }),
  });

export const disableMFA = (current_password: string, code: string) =>
  request<void>("/auth/mfa/disable", {
    method: "POST",
    body: JSON.stringify({ current_password, code }),
  });

export const changePassword = (current_password: string, new_password: string) =>
  request<void>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ current_password, new_password }),
  });

export interface CustomerFilters {
  q: string;
  status: CustomerStatus | "";
  contractStatus: CustomerContractStatus | "";
  includeArchived: boolean;
  sortBy: CustomerSort;
  sortOrder: "asc" | "desc";
  limit: number;
  offset: number;
}

export const getCustomers = (filters: CustomerFilters) => {
  const params = new URLSearchParams({
    limit: String(filters.limit),
    offset: String(filters.offset),
    sort_by: filters.sortBy,
    sort_order: filters.sortOrder,
  });
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.status) params.set("status", filters.status);
  if (filters.contractStatus) params.set("contract_status", filters.contractStatus);
  if (filters.includeArchived) params.set("include_archived", "true");
  return request<CustomerPage>(`/customers?${params}`);
};

export const getDashboard = () => request<Dashboard>("/dashboard");

export type CustomerInput = {
  company_name: string;
  status?: CustomerStatus;
  contract_status?: CustomerContractStatus;
  email?: string;
  phone?: string;
  legal_form?: string;
  website?: string;
  vat_number?: string;
  tax_number?: string;
  internal_notes?: string;
  business_address?: CustomerAddressInput | null;
  billing_address?: CustomerAddressInput | null;
};

export type CustomerUpdateInput = {
  company_name?: string;
  status?: CustomerStatus;
  contract_status?: CustomerContractStatus;
  email?: string | null;
  phone?: string | null;
  legal_form?: string | null;
  website?: string | null;
  vat_number?: string | null;
  tax_number?: string | null;
  internal_notes?: string | null;
  business_address?: CustomerAddressInput | null;
  billing_address?: CustomerAddressInput | null;
};

export const createCustomer = (data: CustomerInput) =>
  request<Customer>("/customers", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const getCustomer = (id: string) => request<Customer>(`/customers/${id}`);

export const getCustomerHistory = (id: string) =>
  request<CustomerHistory[]>(`/customers/${id}/history?limit=100`);

export const updateCustomer = (id: string, data: CustomerUpdateInput) =>
  request<Customer>(`/customers/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const archiveCustomer = (id: string) =>
  request<Customer>(`/customers/${id}/archive`, { method: "POST" });

export const reactivateCustomer = (id: string) =>
  request<Customer>(`/customers/${id}/reactivate`, { method: "POST" });

export const createCustomerContact = (customerId: string, data: CustomerContactInput) =>
  request<CustomerContact>(`/customers/${customerId}/contacts`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateCustomerContact = (
  customerId: string,
  contactId: string,
  data: { is_primary: boolean },
) =>
  request<CustomerContact>(`/customers/${customerId}/contacts/${contactId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const deleteCustomerContact = (customerId: string, contactId: string) =>
  request<void>(`/customers/${customerId}/contacts/${contactId}`, { method: "DELETE" });

export const getUsers = () => request<AuthUser[]>("/users");

export const resetUserPassword = (userId: string, temporary_password: string) =>
  request<void>(`/users/${userId}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ temporary_password }),
  });

export interface EmployeeFilters {
  q: string;
  status: EmployeeStatus | "";
  includeArchived: boolean;
  sortBy: "employee_number" | "full_name" | "hired_on" | "employment_status";
  sortOrder: "asc" | "desc";
  limit: number;
  offset: number;
}

export type EmployeeInput = {
  employee_number: string;
  user_id?: string | null;
  full_name: string;
  email?: string | null;
  phone?: string | null;
  job_title?: string | null;
  employment_status?: EmployeeStatus;
  hired_on: string;
  ended_on?: string | null;
  contract_type?: string | null;
  weekly_hours?: number | null;
};

export type EmployeeUpdateInput = Partial<EmployeeInput>;

export const getEmployees = (filters: EmployeeFilters) => {
  const params = new URLSearchParams({
    limit: String(filters.limit),
    offset: String(filters.offset),
    sort_by: filters.sortBy,
    sort_order: filters.sortOrder,
  });
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.status) params.set("status", filters.status);
  if (filters.includeArchived) params.set("include_archived", "true");
  return request<EmployeePage>(`/employees?${params}`);
};

export const createEmployee = (data: EmployeeInput) =>
  request<Employee>("/employees", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const getEmployee = (id: string) => request<Employee>(`/employees/${id}`);

export const getEmployeeLinkedUserCandidates = (employeeId?: string) =>
  request<EmployeeAccountCandidate[]>(
    `/employees/linked-user-candidates${employeeId ? `?employee_id=${employeeId}` : ""}`,
  );

export const getEmployeeObjectAssignments = (id: string) =>
  request<EmployeeObjectAssignment[]>(`/employees/${id}/objects`);

export const getEmployeeObjectAssignmentHistory = (id: string) =>
  request<EmployeeObjectAssignmentHistory[]>(
    `/employees/${id}/object-assignment-history?limit=100`,
  );

export const getEmployeeObjectAssignmentCandidates = () =>
  request<EmployeeObjectCandidate[]>("/employees/object-assignment-candidates");

export const assignEmployeeToObject = (employeeId: string, objectId: string) =>
  request<EmployeeObjectAssignment[]>(`/employees/${employeeId}/objects/${objectId}`, {
    method: "POST",
  });

export const endEmployeeObjectAssignment = (employeeId: string, objectId: string) =>
  request<EmployeeObjectAssignment[]>(`/employees/${employeeId}/objects/${objectId}`, {
    method: "DELETE",
  });

export const updateEmployee = (id: string, data: EmployeeUpdateInput) =>
  request<Employee>(`/employees/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const archiveEmployee = (id: string) =>
  request<Employee>(`/employees/${id}/archive`, { method: "POST" });

export const reactivateEmployee = (id: string) =>
  request<Employee>(`/employees/${id}/reactivate`, { method: "POST" });

export const getEmployeeQualifications = (id: string, includeArchived = false) =>
  request<EmployeeQualification[]>(
    `/employees/${id}/qualifications${includeArchived ? "?include_archived=true" : ""}`,
  );

export const getEmployeeQualificationDocuments = (employeeId: string) =>
  request<EmployeeQualificationDocument[]>(`/employees/${employeeId}/qualification-documents`);

export const uploadEmployeeQualificationDocument = (
  employeeId: string,
  qualificationId: string,
  file: File,
) => {
  const data = new FormData();
  data.append("document", file);
  return request<EmployeeQualificationDocument>(
    `/employees/${employeeId}/qualifications/${qualificationId}/documents`,
    { method: "POST", body: data },
  );
};

export const employeeQualificationDocumentUrl = (
  employeeId: string,
  qualificationId: string,
  documentId: string,
  download = false,
) =>
  `/api/v1/employees/${employeeId}/qualifications/${qualificationId}/documents/${documentId}${
    download ? "?download=true" : ""
  }`;

export const createEmployeeQualification = (
  id: string,
  data: {
    category: string;
    name: string;
    issuer?: string;
    valid_from?: string;
    expires_on?: string;
  },
) =>
  request<EmployeeQualification>(`/employees/${id}/qualifications`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const archiveEmployeeQualification = (employeeId: string, qualificationId: string) =>
  request<EmployeeQualification>(
    `/employees/${employeeId}/qualifications/${qualificationId}/archive`,
    { method: "POST" },
  );

export const getExpiringEmployeeQualifications = (days = 30) =>
  request<Array<EmployeeQualification & {
    employee_number: string;
    employee_name: string;
    days_until_expiry: number;
  }>>(`/employees/qualifications/expiring?days=${days}`);

export const getEmployeeAbsences = (id: string) =>
  request<EmployeeAbsence[]>(`/employees/${id}/absences`);

export const createEmployeeAbsence = (
  id: string,
  data: {
    absence_type: EmployeeAbsenceType;
    starts_on: string;
    ends_on: string;
    status?: EmployeeAbsenceStatus;
  },
) =>
  request<EmployeeAbsence>(`/employees/${id}/absences`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateEmployeeAbsence = (
  employeeId: string,
  absenceId: string,
  data: { status: EmployeeAbsenceStatus },
) =>
  request<EmployeeAbsence>(`/employees/${employeeId}/absences/${absenceId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const getEmployeePortalProfile = () =>
  request<EmployeePortalProfile>("/employee-portal/me");

export const getEmployeePortalShifts = () =>
  request<EmployeePortalShift[]>("/employee-portal/me/shifts");

export const getEmployeePortalShift = (shiftId: string) =>
  request<EmployeePortalShift>(`/employee-portal/me/shifts/${shiftId}`);

export const getEmployeePortalTasks = () =>
  request<EmployeePortalTask[]>("/employee-portal/me/tasks");

export const getEmployeePortalNotifications = () =>
  request<EmployeePortalNotification[]>("/employee-portal/me/notifications");

export const markEmployeePortalNotificationRead = (notificationId: string) =>
  request<EmployeePortalNotification>(
    `/employee-portal/me/notifications/${notificationId}/read`,
    { method: "PATCH" },
  );

export const getEmployeePortalQualifications = () =>
  request<EmployeePortalQualification[]>("/employee-portal/me/qualifications");

export const getEmployeePortalTimeOverview = (filters: { limit?: number; offset?: number } = {}) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined) params.set(key, String(value));
  }
  return request<EmployeePortalTimeOverview>(`/employee-portal/me/time-entries?${params.toString()}`);
};

export const getEmployeePortalAbsences = () =>
  request<EmployeePortalAbsence[]>("/employee-portal/me/absences");

export const createEmployeePortalAbsence = (data: {
  absence_type: EmployeeAbsenceType;
  starts_on: string;
  ends_on: string;
}) =>
  request<EmployeePortalAbsence>("/employee-portal/me/absences", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateEmployeePortalAbsence = (
  absenceId: string,
  data: {
    absence_type?: EmployeeAbsenceType;
    starts_on?: string;
    ends_on?: string;
  },
) =>
  request<EmployeePortalAbsence>(`/employee-portal/me/absences/${absenceId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const getEmployeePortalAvailabilityRequests = () =>
  request<EmployeePortalAvailabilityRequest[]>("/employee-portal/me/availability-requests");

export const createEmployeePortalAvailabilityRequest = (data: {
  kind: ScheduleAvailabilityRequestKind;
  starts_at_local: string;
  ends_at_local: string;
  starts_at_fold?: 0 | 1;
  ends_at_fold?: 0 | 1;
}) =>
  request<EmployeePortalAvailabilityRequest>("/employee-portal/me/availability-requests", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateEmployeePortalAvailabilityRequest = (
  requestId: string,
  data: {
    kind?: ScheduleAvailabilityRequestKind;
    starts_at_local?: string;
    ends_at_local?: string;
    starts_at_fold?: 0 | 1;
    ends_at_fold?: 0 | 1;
  },
) =>
  request<EmployeePortalAvailabilityRequest>(
    `/employee-portal/me/availability-requests/${requestId}`,
    {
      method: "PATCH",
      body: JSON.stringify(data),
    },
  );

export const getEmployeeSensitiveDetails = (id: string) =>
  request<EmployeeSensitiveDetails>(`/employees/${id}/sensitive`);

export const updateEmployeeSensitiveDetails = (
  id: string,
  data: { address: string | null; emergency_contact: string | null; internal_notes: string | null },
) =>
  request<EmployeeSensitiveDetails>(`/employees/${id}/sensitive`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const getEmployeeHistory = (id: string) =>
  request<EmployeeHistory[]>(`/employees/${id}/history?limit=100`);

export interface ObjectFilters {
  q: string;
  status: ObjectStatus | "";
  customerId: string;
  includeArchived: boolean;
  sortBy: ObjectSort;
  sortOrder: "asc" | "desc";
  limit: number;
  offset: number;
}

export type ObjectInput = {
  customer_id: string;
  name: string;
  code?: string;
  object_type?: string;
  description?: string;
  status?: ObjectStatus;
  operating_hours?: string;
  service_times?: string;
  staffing_requirements?: string;
  address?: ObjectAddressInput;
  contacts?: ObjectContactInput[];
};

export type ObjectUpdateInput = {
  customer_id?: string;
  name?: string;
  code?: string;
  object_type?: string | null;
  description?: string | null;
  status?: ObjectStatus;
  operating_hours?: string | null;
  service_times?: string | null;
  staffing_requirements?: string | null;
  address?: ObjectAddressInput | null;
};

export const getObjects = (filters: ObjectFilters) => {
  const params = new URLSearchParams({
    limit: String(filters.limit),
    offset: String(filters.offset),
    sort_by: filters.sortBy,
    sort_order: filters.sortOrder,
  });
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.status) params.set("status", filters.status);
  if (filters.customerId) params.set("customer_id", filters.customerId);
  if (filters.includeArchived) params.set("include_archived", "true");
  return request<ObjectPage>(`/objects?${params}`);
};

export interface PhysicalKeyFilters {
  q: string;
  status: PhysicalKeyStatus | "";
  object_id: string;
  employee_id: string;
  include_archived: boolean;
  limit: number;
  offset: number;
}

export const getKeys = (filters: PhysicalKeyFilters) => {
  const params = new URLSearchParams({
    limit: String(filters.limit),
    offset: String(filters.offset),
  });
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.status) params.set("status", filters.status);
  if (filters.object_id) params.set("object_id", filters.object_id);
  if (filters.employee_id) params.set("employee_id", filters.employee_id);
  if (filters.include_archived) params.set("include_archived", "true");
  return request<PhysicalKeyPage>(`/keys?${params}`);
};

export const getKeyObjects = () => request<KeyObjectCandidate[]>("/keys/objects");

export const getEligibleKeyEmployees = (objectId: string) =>
  request<KeyEmployeeCandidate[]>(`/keys/eligible-employees?object_id=${encodeURIComponent(objectId)}`);

export const createKey = (data: { key_number: string; description: string; object_id: string }) =>
  request<PhysicalKey>("/keys", { method: "POST", body: JSON.stringify(data) });

export const updateKey = (keyId: string, data: { description: string }) =>
  request<PhysicalKey>(`/keys/${keyId}`, { method: "PATCH", body: JSON.stringify(data) });

export const archiveKey = (keyId: string) =>
  request<PhysicalKey>(`/keys/${keyId}/archive`, { method: "POST" });

export const createKeyMovement = (keyId: string, data: {
  movement_type: KeyMovementType;
  employee_id?: string;
  acknowledged?: boolean;
  acknowledgement_note?: string;
  note?: string;
}) =>
  request<KeyMovement>(`/keys/${keyId}/movements`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const getKeyMovements = (keyId: string, limit = 100, offset = 0) =>
  request<KeyMovementPage>(`/keys/${keyId}/movements?limit=${limit}&offset=${offset}`);

export interface InventoryFilters {
  q: string;
  category: InventoryCategory | "";
  condition: InventoryCondition | "";
  status: InventoryStatus | "";
  object_id: string;
  employee_id: string;
  include_archived: boolean;
  limit: number;
  offset: number;
}

export const getInventoryAssets = (filters: InventoryFilters) => {
  const params = new URLSearchParams({
    limit: String(filters.limit),
    offset: String(filters.offset),
  });
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.category) params.set("category", filters.category);
  if (filters.condition) params.set("condition", filters.condition);
  if (filters.status) params.set("status", filters.status);
  if (filters.object_id) params.set("object_id", filters.object_id);
  if (filters.employee_id) params.set("employee_id", filters.employee_id);
  if (filters.include_archived) params.set("include_archived", "true");
  return request<InventoryAssetPage>(`/inventory/assets?${params}`);
};

export const getInventoryObjects = () =>
  request<InventoryObjectCandidate[]>("/inventory/objects");

export const getInventoryEmployees = () =>
  request<InventoryEmployeeCandidate[]>("/inventory/employees");

export const getInventoryEligibleEmployees = (objectId?: string) => {
  const params = new URLSearchParams();
  if (objectId) params.set("object_id", objectId);
  return request<InventoryEmployeeCandidate[]>(
    `/inventory/eligible-employees${params.size ? `?${params}` : ""}`,
  );
};

export const createInventoryAsset = (data: {
  asset_number: string;
  serial_number?: string;
  name: string;
  category: InventoryCategory;
  condition: InventoryCondition;
  location: string;
  object_id?: string;
}) =>
  request<InventoryAsset>("/inventory/assets", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateInventoryAsset = (
  assetId: string,
  data: {
    serial_number?: string | null;
    name?: string;
    category?: InventoryCategory;
    condition?: InventoryCondition;
    location?: string;
  },
) =>
  request<InventoryAsset>(`/inventory/assets/${assetId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const archiveInventoryAsset = (assetId: string) =>
  request<InventoryAsset>(`/inventory/assets/${assetId}/archive`, { method: "POST" });

export const createInventoryEvent = (
  assetId: string,
  data: {
    event_type: InventoryActionType;
    employee_id?: string;
    object_id?: string | null;
    acknowledged?: boolean;
    acknowledgement_note?: string;
    condition?: InventoryCondition;
    location?: string;
    note?: string;
  },
) =>
  request<InventoryEvent>(`/inventory/assets/${assetId}/events`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const getInventoryEvents = (assetId: string, limit = 100, offset = 0) =>
  request<InventoryEventPage>(
    `/inventory/assets/${assetId}/events?limit=${limit}&offset=${offset}`,
  );

export const getCustomerObjects = (customerId: string) =>
  getObjects({
    q: "",
    status: "",
    customerId,
    includeArchived: true,
    sortBy: "name",
    sortOrder: "asc",
    limit: 100,
    offset: 0,
  });

export const getObject = (id: string) => request<SecurityObject>(`/objects/${id}`);
export const getObjectHistory = (id: string) =>
  request<ObjectHistory[]>(`/objects/${id}/history?limit=100`);

export const createObject = (data: ObjectInput) =>
  request<SecurityObject>("/objects", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateObject = (id: string, data: ObjectUpdateInput) =>
  request<SecurityObject>(`/objects/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const archiveObject = (id: string) =>
  request<SecurityObject>(`/objects/${id}/archive`, { method: "POST" });

export const reactivateObject = (id: string) =>
  request<SecurityObject>(`/objects/${id}/reactivate`, { method: "POST" });

export const createObjectContact = (objectId: string, data: ObjectContactInput) =>
  request<ObjectContact>(`/objects/${objectId}/contacts`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateObjectContact = (
  objectId: string,
  contactId: string,
  data: Partial<ObjectContactInput>,
) =>
  request<ObjectContact>(`/objects/${objectId}/contacts/${contactId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const deleteObjectContact = (objectId: string, contactId: string) =>
  request<void>(`/objects/${objectId}/contacts/${contactId}`, { method: "DELETE" });

export const getObjectSecurity = (id: string) =>
  request<ObjectSecurityDetails>(`/objects/${id}/security`);

export const updateObjectSecurity = (
  id: string,
  data: Partial<Omit<ObjectSecurityDetails, "object_id" | "updated_at">>,
) =>
  request<ObjectSecurityDetails>(`/objects/${id}/security`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const getObjectAssignmentCandidates = () =>
  request<ObjectAssignmentCandidate[]>("/objects/assignment-candidates");

export const getObjectAssignments = (id: string) =>
  request<ObjectAssignment[]>(`/objects/${id}/assignments`);

export const updateObjectAssignments = (id: string, userIds: string[]) =>
  request<ObjectAssignment[]>(`/objects/${id}/assignments`, {
    method: "PUT",
    body: JSON.stringify({ user_ids: userIds }),
  });

export interface ScheduleShiftFilters {
  fromDate: string;
  toDate: string;
  employeeId: string;
  objectId: string;
  includeCancelled?: boolean;
}

export type ScheduleShiftInput = {
  employee_id: string;
  object_id: string;
  starts_at_local: string;
  ends_at_local: string;
  starts_at_fold: number;
  ends_at_fold: number;
  break_minutes: number;
  required_qualification?: string;
};

export const getScheduleSettings = () =>
  request<ScheduleSettings>("/scheduling/settings");

export const getEmployeeAvailability = (employeeId: string) =>
  request<EmployeeAvailabilityWindow[]>(`/scheduling/employees/${employeeId}/availability`);

export const updateEmployeeAvailability = (
  employeeId: string,
  windows: Array<Pick<EmployeeAvailabilityWindow, "weekday" | "starts_at" | "ends_at">>,
) =>
  request<EmployeeAvailabilityWindow[]>(`/scheduling/employees/${employeeId}/availability`, {
    method: "PUT",
    body: JSON.stringify({ windows }),
  });

export const getScheduleAvailabilityRequests = (fromDate: string, toDate: string) => {
  const params = new URLSearchParams({ from_date: fromDate, to_date: toDate });
  return request<ScheduleAvailabilityRequest[]>(`/scheduling/availability-requests?${params}`);
};

export const createScheduleAvailabilityRequest = (data: {
  employee_id?: string;
  kind: ScheduleAvailabilityRequestKind;
  starts_at_local: string;
  ends_at_local: string;
  starts_at_fold: number;
  ends_at_fold: number;
}) =>
  request<ScheduleAvailabilityRequest>("/scheduling/availability-requests", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateScheduleAvailabilityRequest = (
  id: string,
  status: "accepted" | "rejected",
) =>
  request<ScheduleAvailabilityRequest>(`/scheduling/availability-requests/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });

export const updateScheduleSettings = (
  data: Pick<ScheduleSettings, "time_zone" | "minimum_rest_hours">,
) =>
  request<ScheduleSettings>("/scheduling/settings", {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const getScheduleShifts = (filters: ScheduleShiftFilters) => {
  const params = new URLSearchParams({
    from_date: filters.fromDate,
    to_date: filters.toDate,
    limit: "500",
  });
  if (filters.employeeId) params.set("employee_id", filters.employeeId);
  if (filters.objectId) params.set("object_id", filters.objectId);
  if (filters.includeCancelled) params.set("include_cancelled", "true");
  return request<ScheduleShift[]>(`/scheduling/shifts?${params}`);
};

export const createScheduleShift = (data: ScheduleShiftInput) =>
  request<ScheduleShift>("/scheduling/shifts", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateScheduleShift = (
  id: string,
  data: Partial<ScheduleShiftInput>,
) =>
  request<ScheduleShift>(`/scheduling/shifts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const publishScheduleShift = (id: string) =>
  request<ScheduleShift>(`/scheduling/shifts/${id}/publish`, { method: "POST" });

export const cancelScheduleShift = (id: string) =>
  request<ScheduleShift>(`/scheduling/shifts/${id}/cancel`, { method: "POST" });

export const getScheduleShiftHistory = (id: string) =>
  request<ScheduleShiftHistory[]>(`/scheduling/shifts/${id}/history?limit=100`);

export const getScheduleShiftReplacementCandidates = (id: string) =>
  request<ScheduleReplacementCandidate[]>(
    `/scheduling/shifts/${id}/replacement-candidates`,
  );

export const replaceScheduleShiftEmployee = (
  id: string,
  employeeId: string,
  reason: ScheduleReplacementReason,
) =>
  request<ScheduleShift>(`/scheduling/shifts/${id}/replacement`, {
    method: "POST",
    body: JSON.stringify({ employee_id: employeeId, reason }),
  });

export interface TimeEntryFilters {
  fromDate: string;
  toDate: string;
  employeeId?: string;
  objectId?: string;
  customerId?: string;
  status?: string;
  groupBy?: "employee" | "object" | "customer" | "day" | "week" | "month";
}

function timeFilterParams(filters: TimeEntryFilters) {
  const params = new URLSearchParams({
    from_date: filters.fromDate,
    to_date: filters.toDate,
  });
  if (filters.employeeId) params.set("employee_id", filters.employeeId);
  if (filters.objectId) params.set("object_id", filters.objectId);
  if (filters.customerId) params.set("customer_id", filters.customerId);
  if (filters.status) params.set("status", filters.status);
  if (filters.groupBy) params.set("group_by", filters.groupBy);
  return params;
}

export const getTimeEntries = (filters: TimeEntryFilters) =>
  request<TimeEntry[]>(`/time-tracking/entries?${timeFilterParams(filters)}`);

export const getTimeReport = (filters: TimeEntryFilters) =>
  request<TimeEntrySummary>(`/time-tracking/reports?${timeFilterParams(filters)}`);

export const getMissingShifts = (fromDate: string, toDate: string) =>
  request<MissingShift[]>(
    `/time-tracking/reports/missing?${new URLSearchParams({
      from_date: fromDate,
      to_date: toDate,
    })}`,
  );

export const getTimeCorrections = (pendingOnly = true) =>
  request<TimeEntryCorrection[]>(
    `/time-tracking/corrections?pending_only=${String(pendingOnly)}`,
  );

export const startTimeEntry = (data: {
  shift_id?: string;
  employee_id?: string;
  object_id?: string;
}) =>
  request<TimeEntry>("/time-tracking/start", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const pauseTimeEntry = (id: string) =>
  request<TimeEntry>(`/time-tracking/entries/${id}/pause`, { method: "POST" });

export const resumeTimeEntry = (id: string) =>
  request<TimeEntry>(`/time-tracking/entries/${id}/resume`, { method: "POST" });

export const stopTimeEntry = (id: string) =>
  request<TimeEntry>(`/time-tracking/entries/${id}/stop`, { method: "POST" });

export const createManualTimeEntry = (data: {
  employee_id: string;
  object_id: string;
  shift_id?: string;
  segments: Array<{ kind: "work" | "break"; started_at: string; ended_at: string }>;
}) =>
  request<TimeEntry>("/time-tracking/entries/manual", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const requestTimeCorrection = (
  id: string,
  reason: string,
  segments: Array<{ kind: "work" | "break"; started_at: string; ended_at: string }>,
) =>
  request<TimeEntryCorrection>(`/time-tracking/entries/${id}/corrections`, {
    method: "POST",
    body: JSON.stringify({ reason, segments }),
  });

export const approveTimeEntry = (id: string) =>
  request<TimeEntry>(`/time-tracking/entries/${id}/approve`, { method: "POST" });

export const rejectTimeEntry = (id: string, reason: string) =>
  request<TimeEntry>(`/time-tracking/entries/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

export const approveTimeCorrection = (id: string) =>
  request<TimeEntry>(`/time-tracking/corrections/${id}/approve`, { method: "POST" });

export const rejectTimeCorrection = (id: string, reason: string) =>
  request<TimeEntry>(`/time-tracking/corrections/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

export async function exportTimeEntries(filters: TimeEntryFilters): Promise<Blob> {
  const csrf = document.cookie.split("; ").find((cookie) =>
    cookie.startsWith("securityops_csrf="),
  )?.split("=")[1];
  const response = await fetch(`/api/v1/time-tracking/export.csv?${timeFilterParams(filters)}`, {
    credentials: "same-origin",
    headers: csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {},
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : `Serverfehler (${response.status})`,
    );
  }
  return response.blob();
}

export const getTimeTrackingSettings = () =>
  request<{ federal_state: FederalState | null; updated_at: string }>("/time-tracking/settings");

export const updateTimeTrackingSettings = (federalState: FederalState | null) =>
  request<{ federal_state: FederalState | null; updated_at: string }>("/time-tracking/settings", {
    method: "PATCH",
    body: JSON.stringify({ federal_state: federalState }),
  });

export const getTimeSurchargeRules = () =>
  request<TimeSurchargeRule[]>("/time-tracking/surcharge-rules");

export const createTimeSurchargeRule = (data: {
  code: string;
  name: string;
  category: TimeSurchargeCategory;
  calculation_type: "percentage" | "fixed";
  value: string;
  currency: string | null;
  basis_description: string;
  valid_from: string;
  valid_to: string | null;
  priority: number;
  combination_mode: "exclusive" | "combine";
  weekdays: number[];
  starts_local: string | null;
  ends_local: string | null;
}) =>
  request<TimeSurchargeRule>("/time-tracking/surcharge-rules", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const calculateTimeSurcharges = (entryId: string) =>
  request<TimeSurchargeCalculation>(
    `/time-tracking/entries/${entryId}/surcharge-calculations`,
    { method: "POST" },
  );

export const getTimeSurchargeCalculations = (entryId: string) =>
  request<TimeSurchargeCalculation[]>(
    `/time-tracking/entries/${entryId}/surcharge-calculations`,
  );

export const getTimeSurchargeReport = (fromDate: string, toDate: string) =>
  request<TimeSurchargeCalculation[]>(
    `/time-tracking/reports/surcharges?${new URLSearchParams({
      from_date: fromDate,
      to_date: toDate,
    })}`,
  );

export const getLockedTimePeriods = () =>
  request<TimeTrackingPeriod[]>("/time-tracking/periods");

export const lockTimePeriod = (fromDate: string, toDate: string) =>
  request<TimeTrackingPeriod>("/time-tracking/periods/lock", {
    method: "POST",
    body: JSON.stringify({ from_date: fromDate, to_date: toDate }),
  });

export async function exportTimeSurchargeCsv(fromDate: string, toDate: string): Promise<Blob> {
  const csrf = document.cookie.split("; ").find((cookie) =>
    cookie.startsWith("securityops_csrf="),
  )?.split("=")[1];
  const params = new URLSearchParams({ from_date: fromDate, to_date: toDate });
  const response = await fetch(`/api/v1/time-tracking/export-surcharges.csv?${params}`, {
    credentials: "same-origin",
    headers: csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {},
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : `Serverfehler (${response.status})`,
    );
  }
  return response.blob();
}

export interface DocumentFilters {
  q: string;
  status: string;
  category: string;
  includeArchived: boolean;
}

export const getDocuments = (filters: DocumentFilters) => {
  const params = new URLSearchParams({ limit: "100" });
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.status) params.set("status", filters.status);
  if (filters.category) params.set("category", filters.category);
  if (filters.includeArchived) params.set("include_archived", "true");
  return request<DocumentPage>(`/documents?${params}`);
};

export const getDocument = (id: string) => request<ManagedDocument>(`/documents/${id}`);

export const createDocument = (data: FormData) =>
  request<ManagedDocument>("/documents", { method: "POST", body: data });

export const uploadDocumentVersion = (id: string, data: FormData) =>
  request<DocumentVersion>(`/documents/${id}/versions`, {
    method: "POST",
    body: data,
  });

export const updateDocument = (id: string, data: Partial<ManagedDocument>) =>
  request<ManagedDocument>(`/documents/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const archiveDocument = (id: string) =>
  request<ManagedDocument>(`/documents/${id}/archive`, { method: "POST" });

export const restoreDocument = (id: string) =>
  request<ManagedDocument>(`/documents/${id}/restore`, { method: "POST" });

export const requestDocumentApproval = (versionId: string) =>
  request<DocumentApproval>(
    `/documents/versions/${versionId}/approvals`,
    { method: "POST" },
  );

export const decideDocumentApproval = (
  approvalId: string,
  status: "approved" | "rejected",
  decisionNote?: string,
) =>
  request<DocumentApproval>(`/documents/approvals/${approvalId}`, {
    method: "PATCH",
    body: JSON.stringify({ status, decision_note: decisionNote }),
  });

export const acknowledgeDocumentRead = (versionId: string) =>
  request<DocumentReadReceipt>(`/documents/versions/${versionId}/read-receipt`, { method: "POST" });

export const getDocumentApprovals = (statusFilter = "pending") =>
  request<DocumentApprovalQueueItem[]>(
    `/document-approvals?${new URLSearchParams({ status: statusFilter })}`,
  );

export async function downloadDocumentVersion(
  documentId: string,
  versionId: string,
): Promise<Blob> {
  const csrf = document.cookie.split("; ").find((cookie) =>
    cookie.startsWith("securityops_csrf="),
  )?.split("=")[1];
  const response = await fetch(
    `/api/v1/documents/${documentId}/versions/${versionId}/download`,
    {
      credentials: "same-origin",
      headers: csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {},
    },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : `Serverfehler (${response.status})`,
    );
  }
  return response.blob();
}

export interface ContractFilters {
  q: string;
  status: string;
  contractType: ContractType | "";
  includeArchived: boolean;
}

export const getContracts = (filters: ContractFilters) => {
  const params = new URLSearchParams({ limit: "100" });
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.status) params.set("status", filters.status);
  if (filters.contractType) params.set("contract_type", filters.contractType);
  if (filters.includeArchived) params.set("include_archived", "true");
  return request<ContractPage>(`/contracts?${params}`);
};

export const getContract = (id: string) => request<ManagedContract>(`/contracts/${id}`);

export type ContractInput = {
  contract_number: string;
  name: string;
  contract_type: ContractType;
  counterparty: string;
  customer_id: string;
  object_id?: string | null;
  employee_id?: string | null;
  starts_on: string;
  ends_on?: string | null;
  notice_period_days?: number | null;
  renewal_rule?: string | null;
  status: ContractStatus;
  document_id?: string | null;
  internal_notes?: string | null;
};

export const createContract = (data: ContractInput) =>
  request<ManagedContract>("/contracts", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const getOWKSObjects = () => request<OWKSObject[]>("/owks/objects");

export const getOWKSEvents = (objectId: string) =>
  request<OWKSEvent[]>(`/owks/objects/${objectId}/events`);

export const getOWKSEvent = (eventId: string) =>
  request<OWKSEvent>(`/owks/events/${eventId}`);

export const getOWKSControlPoints = (objectId: string) =>
  request<OWKSControlPoint[]>(`/owks/objects/${objectId}/control-points`);

export const createOWKSControlPoint = (
  objectId: string,
  data: { name: string; identifier_type: "qr" | "nfc" },
) =>
  request<OWKSControlPoint>(`/owks/objects/${objectId}/control-points`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const getOWKSRoutes = (objectId: string) =>
  request<OWKSRoute[]>(`/owks/objects/${objectId}/routes`);

export const createOWKSRoute = (
  objectId: string,
  data: { name: string; interval_minutes: number; control_point_ids: string[] },
) =>
  request<OWKSRoute>(`/owks/objects/${objectId}/routes`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const createOWKSEvent = (data: {
  object_id: string;
  event_type: "entry" | "handover" | "deviation" | "notification" | "manipulation";
  title: string;
  description: string;
  severity: "info" | "warning" | "critical";
  client_event_id: string;
}) =>
  request<OWKSEvent>("/owks/events", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const syncOWKSEvents = (data: Array<{
  object_id: string;
  event_type: "entry" | "handover" | "deviation" | "notification" | "manipulation" | "control";
  title: string;
  description: string;
  severity: "info" | "warning" | "critical";
  occurred_at: string;
  client_event_id: string;
}>) =>
  request<OWKSSyncResult[]>("/owks/events/sync", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const createOWKSChallenge = (objectId: string) =>
  request<{ id: string; object_id: string; expires_at: string }>(
    `/owks/objects/${objectId}/challenges`,
    { method: "POST" },
  );

export const recordOWKSScan = (data: {
  challenge_id: string;
  credential: string;
  client_event_id: string;
  route_id?: string;
}) =>
  request<OWKSEvent>("/owks/scans", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateContract = (id: string, data: Partial<ContractInput>) =>
  request<ManagedContract>(`/contracts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const archiveContract = (id: string) =>
  request<ManagedContract>(`/contracts/${id}/archive`, { method: "POST" });

export const restoreContract = (id: string) =>
  request<ManagedContract>(`/contracts/${id}/restore`, { method: "POST" });

export const getReminders = (statusFilter = "open") =>
  request<ManagedReminder[]>(`/reminders?${new URLSearchParams({ status: statusFilter })}`);

export const generateReminders = () =>
  request<{ created: number }>("/reminders/generate", { method: "POST" });

export const updateReminder = (id: string, status: "completed" | "dismissed") =>
  request<ManagedReminder>(`/reminders/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });

export const getReminderSettings = () => request<ReminderSettings>("/reminders/settings");

export const updateReminderSettings = (leadDays: number[]) =>
  request<ReminderSettings>("/reminders/settings", {
    method: "PUT",
    body: JSON.stringify({ lead_days: leadDays }),
  });

export const updateOWKSEventStatus = (eventId: string, status: "open" | "in_progress" | "resolved") =>
  request<OWKSEvent>(`/owks/events/${eventId}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });

export const monitorOWKSRoute = (routeId: string) =>
  request<OWKSEvent[]>(`/owks/routes/${routeId}/monitor`, { method: "POST" });

export const uploadOWKSAttachment = (eventId: string, file: File) => {
  const form = new FormData();
  form.append("document", file);
  return request<OWKSAttachment>(
    `/owks/events/${eventId}/attachments`,
    { method: "POST", body: form },
  );
};

export const getOWKSAttachments = (eventId: string) =>
  request<OWKSAttachment[]>(`/owks/events/${eventId}/attachments`);

export const owksAttachmentUrl = (eventId: string, attachmentId: string, download = false) => {
  const params = download ? "?download=true" : "";
  return `/api/v1/owks/events/${eventId}/attachments/${attachmentId}${params}`;
};
