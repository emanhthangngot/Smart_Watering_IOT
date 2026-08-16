import { createContext } from "react";
import type { FarmOpsApi } from "../api/client";
import type { FarmState, HealthStatus, InspectionTask, TrustVerdict } from "../api/types";
import type { PollingResource } from "../hooks/usePollingResource";

export interface OperationsValue {
  api: FarmOpsApi;
  farmState: PollingResource<FarmState>;
  health: PollingResource<HealthStatus>;
  trust: PollingResource<TrustVerdict[]>;
  tasks: PollingResource<InspectionTask[]>;
  refreshAll: () => void;
}

export const OperationsContext = createContext<OperationsValue | undefined>(undefined);
