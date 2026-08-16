import { useCallback, useMemo, type ReactNode } from "react";
import { FarmOpsApi } from "../api/client";
import { usePollingResource } from "../hooks/usePollingResource";
import { OperationsContext, type OperationsValue } from "./operations-context";
import { usePreferences } from "./usePreferences";

export function OperationsProvider({ children }: { children: ReactNode }) {
  const { operatorToken } = usePreferences();
  const api = useMemo(() => new FarmOpsApi(operatorToken), [operatorToken]);
  const loadFarmState = useCallback((signal: AbortSignal) => api.getFarmState(signal), [api]);
  const loadHealth = useCallback((signal: AbortSignal) => api.getHealth(signal), [api]);
  const loadTrust = useCallback((signal: AbortSignal) => api.getTrust(signal), [api]);
  const loadTasks = useCallback((signal: AbortSignal) => api.getTasks(signal), [api]);
  const farmState = usePollingResource(loadFarmState);
  const health = usePollingResource(loadHealth);
  const trust = usePollingResource(loadTrust);
  const tasks = usePollingResource(loadTasks);

  const refreshAll = useCallback(() => {
    farmState.refresh();
    health.refresh();
    trust.refresh();
    tasks.refresh();
  }, [farmState, health, tasks, trust]);

  const value = useMemo<OperationsValue>(() => ({
    api,
    farmState,
    health,
    trust,
    tasks,
    refreshAll,
  }), [api, farmState, health, refreshAll, tasks, trust]);

  return <OperationsContext.Provider value={value}>{children}</OperationsContext.Provider>;
}
