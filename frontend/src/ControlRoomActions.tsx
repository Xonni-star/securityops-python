import { useState } from "react";
import IncidentManagement from "./IncidentManagement";
import SchedulingManagement from "./SchedulingManagement";
import TaskManagement from "./TaskManagement";
import ControlRoomEmployeeSearch from "./ControlRoomEmployeeSearch";
import type { AuthUser } from "./types";

type ActionId = "employees" | "scheduling" | "tasks" | "incidents";

export default function ControlRoomActions({ user }: { user: AuthUser }) {
  const [activeAction, setActiveAction] = useState<ActionId | "">("");
  const allActions: Array<{ id: ActionId; label: string; available: boolean }> = [
    { id: "employees", label: "Mitarbeiter suchen", available: user.permissions.includes("employees.read") },
    {
      id: "scheduling",
      label: "Dienste bearbeiten",
      available: user.permissions.includes("scheduling.read"),
    },
    {
      id: "tasks",
      label: "Aufgaben bearbeiten",
      available: user.permissions.some((permission) =>
        ["tasks.read_own", "tasks.read_all", "tasks.manage_all", "tasks.create"].includes(permission),
      ),
    },
    {
      id: "incidents",
      label: "Vorfälle bearbeiten",
      available: user.permissions.some((permission) =>
        ["incidents.read", "incidents.read_all", "incidents.manage_all", "incidents.create"].includes(permission),
      ),
    },
  ];
  const actions = allActions.filter((action) => action.available);

  if (actions.length === 0) return null;

  return (
    <section className="control-room-actions panel" aria-labelledby="control-room-actions-title">
      <div>
        <p className="eyebrow">OPERATIVE BEARBEITUNG</p>
        <h3 id="control-room-actions-title">Leitstellenaktionen</h3>
      </div>
      <div className="control-room-action-tabs" role="tablist" aria-label="Leitstellenaktionen">
        {actions.map((action) => (
          <button
            key={action.id}
            type="button"
            className={activeAction === action.id ? "secondary-button active" : "secondary-button"}
            role="tab"
            aria-selected={activeAction === action.id}
            aria-controls="control-room-action-panel"
            onClick={() => setActiveAction(action.id)}
          >
            {action.label}
          </button>
        ))}
      </div>
      {activeAction && <div
        id="control-room-action-panel"
        className="control-room-action-panel"
        role="tabpanel"
        aria-label={actions.find((action) => action.id === activeAction)?.label}
      >
        {activeAction === "employees" && <ControlRoomEmployeeSearch />}
        {activeAction === "scheduling" && <SchedulingManagement user={user} />}
        {activeAction === "tasks" && <TaskManagement user={user} />}
        {activeAction === "incidents" && <IncidentManagement user={user} />}
      </div>}
    </section>
  );
}
