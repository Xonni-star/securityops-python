export type CustomerStatus = "active" | "inactive" | "lead";
export type CustomerContractStatus = "none" | "draft" | "active" | "expired" | "terminated";
export type CustomerSort =
  | "company_name"
  | "customer_number"
  | "created_at"
  | "status"
  | "contract_status";
export type ObjectStatus = "active" | "inactive";
export type ObjectSort = "name" | "code" | "created_at" | "status";
export type PhysicalKeyStatus = "available" | "issued" | "lost" | "defective" | "archived";
export type KeyMovementType = "issued" | "returned" | "lost" | "defective" | "inventory";
export type TaskPriority = "low" | "normal" | "high" | "urgent";
export type TaskStatus = "open" | "in_progress" | "blocked" | "completed" | "cancelled";
export type IncidentType =
  | "incident"
  | "accident"
  | "assault"
  | "property_damage"
  | "complaint"
  | "other";
export type IncidentSeverity = "low" | "medium" | "high" | "critical";
export type IncidentStatus = "reported" | "investigating" | "action_required" | "closed";
export type IncidentMeasureStatus = "open" | "in_progress" | "completed";

export interface IncidentItem {
  id: string;
  title: string;
  report: string;
  incident_type: IncidentType;
  severity: IncidentSeverity;
  object_id: string;
  object_name: string;
  status: IncidentStatus;
  due_at: string | null;
  assigned_to_id: string;
  assigned_to_name: string;
  owks_event_id: string | null;
  created_by_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface IncidentSensitiveDetails {
  narrative: string | null;
  closure_report: string | null;
  updated_by_id: string | null;
  updated_at: string | null;
}

export interface IncidentPerson {
  id: string;
  name: string;
  role: "involved" | "witness";
  notes: string | null;
  created_at: string;
}

export interface IncidentAttachment {
  id: string;
  file_name: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
}

export interface IncidentMeasure {
  id: string;
  title: string;
  description: string | null;
  due_at: string | null;
  assigned_to_id: string;
  status: IncidentMeasureStatus;
  created_at: string;
  updated_at: string;
}

export interface IncidentHistory {
  id: string;
  actor_id: string | null;
  action: string;
  changes: Record<string, unknown>;
  created_at: string;
}

export interface IncidentDetail extends IncidentItem {
  sensitive_details: IncidentSensitiveDetails | null;
  people: IncidentPerson[];
  attachments: IncidentAttachment[];
  measures: IncidentMeasure[];
  history: IncidentHistory[];
}

export interface IncidentPage {
  items: IncidentItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface IncidentChoices {
  objects: Array<{ id: string; name: string; code: string }>;
  assignees: Array<{ id: string; full_name: string }>;
  linked_owks_event_ids: string[];
}

export interface ControlRoomObject {
  id: string;
  code: string;
  name: string;
}

export interface ControlRoomShift {
  id: string;
  employee_id: string;
  employee_name: string;
  object_id: string;
  object_name: string;
  starts_at: string;
  ends_at: string;
  status: "published";
}

export interface ControlRoomOWKSEvent {
  id: string;
  object_id: string;
  object_name: string;
  event_type: string;
  severity: string;
  title: string;
  occurred_at: string;
  status: "open" | "in_progress";
}

export interface ControlRoomIncident {
  id: string;
  title: string;
  object_id: string;
  object_name: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  due_at: string | null;
  assigned_to_name: string;
  created_at: string;
}

export interface ControlRoomTask {
  id: string;
  title: string;
  object_id: string | null;
  object_name: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_at: string | null;
  assigned_to_name: string;
  created_at: string;
}

export interface ControlRoomAbsence {
  employee_id: string;
  employee_name: string;
  absence_type: EmployeeAbsenceType;
  status: EmployeeAbsenceStatus;
  starts_on: string;
  ends_on: string;
}

export interface ControlRoomQualification {
  employee_id: string;
  employee_name: string;
  category: string;
  name: string;
  expires_on: string;
}

export interface ControlRoomBillingApproval {
  id: string;
  invoice_number: string;
  object_name: string;
  issued_on: string;
  created_at: string;
}

export interface ControlRoom {
  generated_at: string;
  range_start: string;
  range_end: string;
  counts: Record<string, number>;
  objects?: ControlRoomObject[];
  shifts?: ControlRoomShift[];
  owks_events?: ControlRoomOWKSEvent[];
  incidents?: ControlRoomIncident[];
  tasks?: ControlRoomTask[];
  absences?: ControlRoomAbsence[];
  qualifications?: ControlRoomQualification[];
  billing_approvals?: ControlRoomBillingApproval[];
}

export type EmployeeStatus = "active" | "inactive" | "leave" | "terminated";
export type EmployeeAbsenceType = "vacation" | "sick_leave" | "other";
export type EmployeeAbsenceStatus = "pending" | "approved" | "rejected";
export type ScheduleShiftStatus = "draft" | "published" | "cancelled";
export type TimeEntryStatus =
  | "open"
  | "submitted"
  | "approved"
  | "rejected"
  | "correction_requested"
  | "locked";
export type OWKSEventType =
  | "entry"
  | "handover"
  | "control"
  | "manipulation"
  | "deviation"
  | "missed"
  | "notification"
  | "correction";
export type OWKSEventStatus = "open" | "in_progress" | "resolved";

export interface OWKSObject {
  id: string;
  code: string;
  name: string;
}

export interface OWKSControlPoint {
  id: string;
  object_id: string;
  name: string;
  identifier_type: "qr" | "nfc";
  is_active: boolean;
  created_at: string;
  credential?: string | null;
}

export interface OWKSRoute {
  id: string;
  object_id: string;
  name: string;
  interval_minutes: number;
  is_active: boolean;
  control_point_ids: string[];
  created_at: string;
}

export interface OWKSEvent {
  id: string;
  object_id: string;
  route_id: string | null;
  control_point_id: string | null;
  corrects_event_id: string | null;
  employee_id: string | null;
  actor_id: string | null;
  client_event_id: string | null;
  event_type: OWKSEventType;
  severity: "info" | "warning" | "critical";
  title: string;
  description: string;
  occurred_at: string;
  sync_status: "synced" | "conflict";
  presence_verified: boolean;
  status: OWKSEventStatus;
  created_at: string;
}

export interface OWKSAttachment {
  id: string;
  event_id: string;
  file_name: string;
  media_type: "application/pdf" | "image/jpeg" | "image/png";
  size_bytes: number;
  sha256: string;
  uploaded_by_id: string | null;
  created_at: string;
}

export interface OWKSSyncResult {
  client_event_id: string;
  status: "synced" | "conflict" | "duplicate";
  event: OWKSEvent | null;
  detail: string | null;
}

export type BillingRateKind = "hourly" | "flat" | "surcharge";
export type BillingInvoiceStatus = "draft" | "approved" | "archived";

export interface BillingRate {
  id: string;
  code: string;
  name: string;
  kind: BillingRateKind;
  unit: string;
  unit_price: string;
  tax_code: string;
  tax_rate: string;
  currency: string;
  is_active: boolean;
}

export interface BillingInvoiceLine {
  id: string;
  position: number;
  description: string;
  kind: BillingRateKind;
  quantity: string;
  unit: string;
  unit_price: string;
  tax_code: string;
  tax_rate: string;
  net_amount: string;
  tax_amount: string;
  gross_amount: string;
}

export interface BillingInvoice {
  id: string;
  invoice_number: string;
  customer_id: string;
  contract_id: string | null;
  kind: "invoice" | "correction" | "cancellation";
  status: BillingInvoiceStatus;
  payment_status: "open" | "partial" | "paid";
  dunning_status: "none" | "reminder_1" | "reminder_2" | "final";
  currency: string;
  issued_on: string;
  due_on: string;
  correction_of_id: string | null;
  correction_reason: string | null;
  net_amount: string;
  tax_amount: string;
  gross_amount: string;
  approved_at: string | null;
  archived_at: string | null;
  created_at: string;
  lines: BillingInvoiceLine[];
}

export interface CustomerAddress {
  id: string;
  street: string;
  house_number: string;
  postal_code: string;
  city: string;
  country_code: string;
}

export interface CustomerContact {
  id: string;
  first_name: string;
  last_name: string;
  responsibility: string | null;
  email: string | null;
  phone: string | null;
  is_primary: boolean;
}

export interface CustomerContactInput {
  first_name: string;
  last_name: string;
  responsibility?: string;
  email?: string;
  phone?: string;
  is_primary: boolean;
}

export interface Customer {
  id: string;
  customer_number: string;
  company_name: string;
  status: CustomerStatus;
  contract_status: CustomerContractStatus;
  email: string | null;
  phone: string | null;
  legal_form: string | null;
  website: string | null;
  vat_number: string | null;
  tax_number: string | null;
  internal_notes: string | null;
  archived_at: string | null;
  business_address: CustomerAddress | null;
  billing_address: CustomerAddress | null;
  contacts: CustomerContact[];
  created_at: string;
  updated_at: string;
}

export interface CustomerHistory {
  id: string;
  actor_id: string | null;
  action: string;
  changed_fields: string[];
  created_at: string;
}

export interface CustomerAddressInput {
  street: string;
  house_number: string;
  postal_code: string;
  city: string;
  country_code: string;
}

export interface CustomerPage {
  items: Customer[];
  total: number;
  limit: number;
  offset: number;
}

export interface Employee {
  id: string;
  employee_number: string;
  user_id: string | null;
  full_name: string;
  email: string | null;
  phone: string | null;
  job_title: string | null;
  employment_status: EmployeeStatus;
  hired_on: string;
  ended_on: string | null;
  contract_type: string | null;
  weekly_hours: string | null;
  assigned_objects: string[];
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmployeePortalProfile {
  full_name: string;
  job_title: string | null;
}

export interface EmployeePortalShift {
  id: string;
  object_code: string;
  object_name: string;
  starts_at: string;
  ends_at: string;
  break_minutes: number;
}

export interface EmployeePortalTask {
  id: string;
  title: string;
  due_at: string | null;
  priority: TaskPriority;
  status: TaskStatus;
}

export interface EmployeePortalNotification {
  id: string;
  event_type: NotificationEventType;
  title: string;
  body: string;
  created_at: string;
  read_at: string | null;
}

export interface EmployeePortalQualification {
  id: string;
  category: string;
  name: string;
  issuer: string | null;
  valid_from: string | null;
  expires_on: string | null;
}

export interface EmployeePortalTimeEntry {
  id: string;
  started_at: string;
  ended_at: string | null;
  status: TimeEntryStatus;
  actual_work_seconds: number;
}

export interface EmployeePortalTimeOverview {
  items: EmployeePortalTimeEntry[];
  total: number;
  total_work_seconds: number;
  limit: number;
  offset: number;
}

export type EmployeePortalAbsenceType = EmployeeAbsenceType;

export interface EmployeePortalRequestHistory {
  event: "requested" | "updated" | "approved" | "accepted" | "rejected";
  occurred_at: string;
}

export interface EmployeePortalAbsence {
  id: string;
  absence_type: EmployeeAbsenceType;
  starts_on: string;
  ends_on: string;
  status: EmployeeAbsenceStatus;
  created_at: string;
  updated_at: string;
  history: EmployeePortalRequestHistory[];
}

export interface EmployeePortalAvailabilityRequest {
  id: string;
  kind: ScheduleAvailabilityRequestKind;
  starts_at: string;
  ends_at: string;
  time_zone: string;
  status: ScheduleAvailabilityRequestStatus;
  created_at: string;
  updated_at: string;
  reviewed_at: string | null;
  history: EmployeePortalRequestHistory[];
}

export interface EmployeePage {
  items: Employee[];
  total: number;
  limit: number;
  offset: number;
}

export interface EmployeeQualification {
  id: string;
  employee_id: string;
  category: string;
  name: string;
  issuer: string | null;
  valid_from: string | null;
  expires_on: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmployeeAccountCandidate {
  id: string;
  username: string;
  full_name: string;
}

export interface EmployeeObjectAssignment {
  object_id: string;
  object_code: string;
  object_name: string;
  assigned_at: string;
}

export interface EmployeeObjectCandidate {
  object_id: string;
  object_code: string;
  object_name: string;
}

export interface EmployeeObjectAssignmentHistory {
  id: string;
  object_id: string;
  object_code: string;
  object_name: string;
  action: "assigned" | "ended";
  actor_id: string | null;
  created_at: string;
}

export interface EmployeeQualificationDocument {
  id: string;
  qualification_id: string;
  version: number;
  file_name: string;
  media_type: "application/pdf" | "image/jpeg" | "image/png";
  size_bytes: number;
  sha256: string;
  uploaded_by_id: string | null;
  created_at: string;
}

export interface EmployeeAbsence {
  id: string;
  employee_id: string;
  absence_type: EmployeeAbsenceType;
  starts_on: string;
  ends_on: string;
  status: EmployeeAbsenceStatus;
  created_by_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmployeeSensitiveDetails {
  employee_id: string;
  address: string | null;
  emergency_contact: string | null;
  internal_notes: string | null;
  updated_at: string | null;
}

export interface EmployeeHistory {
  id: string;
  actor_id: string | null;
  action: string;
  changed_fields: string[];
  created_at: string;
}

export interface Dashboard {
  customers_total: number;
  customers_active: number;
  customers_leads: number;
}

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  full_name: string;
  is_active: boolean;
  roles: string[];
  permissions: string[];
}

export interface TaskItem {
  id: string;
  title: string;
  description: string | null;
  assigned_to_id: string;
  assigned_to_name: string;
  created_by_id: string | null;
  created_by_name: string | null;
  customer_id: string | null;
  customer_name: string | null;
  object_id: string | null;
  object_name: string | null;
  due_at: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  completion_evidence: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskComment {
  id: string;
  author_id: string | null;
  author_name: string | null;
  body: string;
  created_at: string;
}

export interface TaskHistory {
  id: string;
  actor_id: string | null;
  actor_name: string | null;
  action: string;
  changes: Record<string, unknown>;
  created_at: string;
}

export interface TaskDetail extends TaskItem {
  comments: TaskComment[];
  history: TaskHistory[];
}

export interface TaskPage {
  items: TaskItem[];
  total: number;
  limit: number;
  offset: number;
}

export type NotificationEventType = "task.assigned" | "task.status_changed";

export interface NotificationItem {
  id: string;
  task_id: string;
  event_type: NotificationEventType;
  title: string;
  body: string;
  created_at: string;
  read_at: string | null;
}

export interface NotificationPage {
  items: NotificationItem[];
  total: number;
  unread_count: number;
  limit: number;
  offset: number;
}

export interface TaskAssignee {
  id: string;
  full_name: string;
}

export interface TaskLocations {
  customers: Array<{ id: string; company_name: string }>;
  objects: Array<{
    id: string;
    name: string;
    customer_id: string;
    customer_name: string;
  }>;
}

export interface Session {
  user: AuthUser;
  password_change_required?: boolean;
}

export interface UserSession {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  absolute_expires_at: string;
  ip_address: string | null;
  user_agent: string | null;
  is_current: boolean;
}

export interface MFAStatus {
  enabled: boolean;
}

export interface MFASetup {
  secret: string;
  otpauth_uri: string;
}

export interface ObjectAddress {
  id: string;
  street: string;
  house_number: string;
  postal_code: string;
  city: string;
  country_code: string;
}

export interface ObjectAddressInput {
  street: string;
  house_number: string;
  postal_code: string;
  city: string;
  country_code: string;
}

export interface ObjectContact {
  id: string;
  first_name: string;
  last_name: string;
  role: string | null;
  email: string | null;
  phone: string | null;
  is_primary: boolean;
}

export interface ObjectContactInput {
  first_name: string;
  last_name: string;
  role?: string | null;
  email?: string | null;
  phone?: string | null;
  is_primary: boolean;
}

export interface SecurityObject {
  id: string;
  customer_id: string;
  customer_name: string;
  code: string;
  name: string;
  object_type: string | null;
  description: string | null;
  status: ObjectStatus;
  operating_hours: string | null;
  service_times: string | null;
  staffing_requirements: string | null;
  archived_at: string | null;
  address: ObjectAddress | null;
  contacts: ObjectContact[];
  created_at: string;
  updated_at: string;
}

export interface ObjectPage {
  items: SecurityObject[];
  total: number;
  limit: number;
  offset: number;
}

export interface PhysicalKey {
  id: string;
  key_number: string;
  description: string;
  object_id: string;
  object_code: string;
  object_name: string;
  status: PhysicalKeyStatus;
  current_employee_id: string | null;
  current_employee_name: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PhysicalKeyPage {
  items: PhysicalKey[];
  total: number;
  limit: number;
  offset: number;
}

export interface KeyMovement {
  id: string;
  key_id: string;
  key_number: string;
  object_id: string;
  employee_id: string | null;
  employee_name: string | null;
  actor_id: string;
  actor_name: string;
  movement_type: KeyMovementType;
  key_status_after: Exclude<PhysicalKeyStatus, "archived">;
  acknowledged_at: string | null;
  acknowledgement_note: string | null;
  note: string | null;
  created_at: string;
}

export interface KeyMovementPage {
  items: KeyMovement[];
  total: number;
  limit: number;
  offset: number;
}

export interface KeyEmployeeCandidate {
  id: string;
  employee_number: string;
  full_name: string;
}

export interface KeyObjectCandidate {
  id: string;
  code: string;
  name: string;
}

export interface ObjectHistory {
  id: string;
  actor_id: string | null;
  action: string;
  changed_fields: string[];
  created_at: string;
}

export interface ObjectSecurityDetails {
  object_id: string;
  security_requirements: string | null;
  access_information: string | null;
  emergency_contact: string | null;
  updated_at: string | null;
}

export interface ObjectAssignment {
  user_id: string;
  username: string;
  full_name: string;
  assigned_at: string;
}

export interface ObjectAssignmentCandidate {
  id: string;
  username: string;
  full_name: string;
}

export interface ScheduleSettings {
  time_zone: string;
  minimum_rest_hours: number;
  updated_at: string;
}

export interface EmployeeAvailabilityWindow {
  id: string;
  employee_id: string;
  weekday: number;
  starts_at: string;
  ends_at: string;
}

export type ScheduleAvailabilityRequestKind = "preferred" | "blocked";
export type ScheduleAvailabilityRequestStatus = "open" | "accepted" | "rejected";
export type ScheduleReplacementReason =
  | "short_notice"
  | "schedule_change"
  | "employee_request"
  | "qualification"
  | "other";

export interface ScheduleAvailabilityRequest {
  id: string;
  employee_id: string;
  employee_name: string;
  employee_number: string;
  kind: ScheduleAvailabilityRequestKind;
  starts_at: string;
  ends_at: string;
  time_zone: string;
  status: ScheduleAvailabilityRequestStatus;
  conflicting_shift_ids: string[];
  created_by_id: string | null;
  reviewed_by_id: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduleShift {
  id: string;
  employee_id: string;
  employee_number: string;
  employee_name: string;
  object_id: string;
  object_code: string;
  object_name: string;
  starts_at: string;
  ends_at: string;
  time_zone: string;
  break_minutes: number;
  required_qualification: string | null;
  status: ScheduleShiftStatus;
  created_by_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduleShiftHistory {
  id: string;
  actor_id: string | null;
  action: string;
  changed_fields: string[];
  details: Record<string, unknown>;
  created_at: string;
}

export interface TimeEntrySegment {
  id: string;
  position: number;
  kind: "work" | "break";
  started_at: string;
  ended_at: string | null;
}

export interface TimeEntryCorrection {
  id: string;
  entry_id: string;
  reason: string;
  status: "pending" | "approved" | "rejected";
  rejection_reason: string | null;
  requested_by_id: string | null;
  decided_by_id: string | null;
  requested_at: string;
  decided_at: string | null;
  segments: TimeEntrySegment[];
}

export interface TimeEntry {
  id: string;
  employee_id: string;
  employee_number: string;
  employee_name: string;
  object_id: string;
  object_code: string;
  object_name: string;
  customer_id: string;
  customer_name: string;
  shift_id: string | null;
  planned_start_at: string | null;
  planned_end_at: string | null;
  planned_break_seconds: number;
  time_zone: string;
  started_at: string;
  ended_at: string | null;
  status: TimeEntryStatus;
  actual_work_seconds: number;
  actual_break_seconds: number;
  planned_work_seconds: number | null;
  difference_seconds: number | null;
  start_deviation_seconds: number | null;
  end_deviation_seconds: number | null;
  created_by_id: string | null;
  submitted_at: string | null;
  reviewed_by_id: string | null;
  reviewed_at: string | null;
  decision_reason: string | null;
  segments: TimeEntrySegment[];
  corrections: TimeEntryCorrection[];
}

export interface TimeEntrySummary {
  from_date: string;
  to_date: string;
  time_zone: string;
  group_by: "employee" | "object" | "customer" | "day" | "week" | "month" | null;
  entry_count: number;
  actual_work_seconds: number;
  actual_break_seconds: number;
  planned_work_seconds: number;
  difference_seconds: number;
  overtime_seconds: number;
  pending_count: number;
  groups: Array<{
    key: string;
    label: string;
    entry_count: number;
    actual_work_seconds: number;
    actual_break_seconds: number;
    planned_work_seconds: number;
    difference_seconds: number;
    overtime_seconds: number;
    pending_count: number;
  }>;
  items: TimeEntry[];
}

export interface MissingShift {
  shift_id: string;
  employee_id: string;
  employee_number: string;
  employee_name: string;
  object_id: string;
  object_code: string;
  object_name: string;
  starts_at: string;
  ends_at: string;
  time_zone: string;
}

export type FederalState =
  | "BW" | "BY" | "BE" | "BB" | "HB" | "HH" | "HE" | "MV"
  | "NI" | "NW" | "RP" | "SL" | "SN" | "ST" | "SH" | "TH";

export type TimeSurchargeCategory =
  | "night" | "saturday" | "sunday" | "public_holiday" | "business";

export interface TimeSurchargeRule {
  id: string;
  code: string;
  name: string;
  category: TimeSurchargeCategory;
  calculation_type: "percentage" | "fixed";
  value: number | string;
  currency: string | null;
  basis_description: string;
  valid_from: string;
  valid_to: string | null;
  priority: number;
  combination_mode: "exclusive" | "combine";
  weekdays: number[];
  starts_local: string | null;
  ends_local: string | null;
  created_by_id: string | null;
  created_at: string;
}

export interface TimeSurchargeAllocation {
  rule_id: string | null;
  rule_code: string | null;
  rule_name: string;
  eligible_work_seconds: number | string;
  configured_value: number | string | null;
  calculation_type: "percentage" | "fixed" | null;
  currency: string | null;
  basis_description: string | null;
  calculated_amount: number | string | null;
  calculation_note: string;
}

export interface TimeSurchargeCalculation {
  id: string;
  entry_id: string;
  version: number;
  gross_work_seconds: number | string;
  time_zone: string;
  federal_state: FederalState | null;
  rule_snapshot: Array<Record<string, unknown>>;
  allocation_snapshot: TimeSurchargeAllocation[];
  source_segments: Array<{ kind: "work"; started_at: string; ended_at: string }>;
  created_by_id: string | null;
  created_at: string;
}

export interface TimeTrackingPeriod {
  id: string;
  from_date: string;
  to_date: string;
  time_zone: string;
  federal_state: FederalState | null;
  locked_by_id: string | null;
  locked_at: string;
}

export type DocumentStatus = "draft" | "active" | "expired" | "archived";
export type ContractType =
  | "customer" | "object" | "personnel" | "service" | "additional" | "other";
export type ContractStatus = "draft" | "active" | "terminated" | "expired" | "archived";
export type ApprovalStatus = "pending" | "approved" | "rejected";
export type ReminderStatus = "open" | "completed" | "dismissed";

export interface DocumentVersion {
  id: string;
  document_id: string;
  version: number;
  file_name: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
  uploaded_by_id: string | null;
  created_at: string;
}

export interface DocumentApproval {
  id: string;
  version_id: string;
  requested_by_id: string | null;
  decided_by_id: string | null;
  status: ApprovalStatus;
  decision_note: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface DocumentApprovalQueueItem extends DocumentApproval {
  document_id: string;
  document_number: string;
  document_title: string;
  version: number;
}

export interface DocumentReadReceipt {
  id: string;
  version_id: string;
  user_id: string;
  read_at: string;
}

export interface DocumentHistory {
  id: string;
  actor_id: string | null;
  action: string;
  changed_fields: string[];
  details: Record<string, unknown>;
  created_at: string;
}

export interface ManagedDocument {
  id: string;
  document_number: string;
  title: string;
  description: string | null;
  category: string;
  status: DocumentStatus;
  customer_id: string | null;
  object_id: string | null;
  employee_id: string | null;
  expires_on: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  latest_version: DocumentVersion | null;
  versions?: DocumentVersion[];
  approvals?: DocumentApproval[];
  read_receipts?: DocumentReadReceipt[];
  history?: DocumentHistory[];
}

export interface DocumentPage {
  items: ManagedDocument[];
  total: number;
  limit: number;
  offset: number;
}

export interface ContractHistory {
  id: string;
  actor_id: string | null;
  action: string;
  changed_fields: string[];
  details: Record<string, unknown>;
  created_at: string;
}

export interface ManagedContract {
  id: string;
  contract_number: string;
  name: string;
  contract_type: ContractType;
  counterparty: string;
  customer_id: string;
  object_id: string | null;
  employee_id: string | null;
  starts_on: string;
  ends_on: string | null;
  notice_period_days: number | null;
  renewal_rule: string | null;
  status: ContractStatus;
  document_id: string | null;
  internal_notes: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  history: ContractHistory[];
}

export interface ContractPage {
  items: ManagedContract[];
  total: number;
  limit: number;
  offset: number;
}

export type ReminderType =
  | "document_expiry" | "contract_expiry" | "contract_termination" | "contract_renewal";

export interface ManagedReminder {
  id: string;
  document_id: string | null;
  contract_id: string | null;
  reminder_type: ReminderType;
  event_on: string;
  remind_on: string;
  status: ReminderStatus;
  created_at: string;
  subject: string;
  number: string;
}

export interface ReminderSettings {
  lead_days: number[];
  updated_by_id: string | null;
  updated_at: string | null;
}
