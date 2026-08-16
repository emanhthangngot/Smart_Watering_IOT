import { BrowserRouter, Route, Routes } from "react-router-dom";
import { NotFoundPage } from "../pages/NotFoundPage";
import { OverviewPage } from "../pages/OverviewPage";
import { PlanPage } from "../pages/PlanPage";
import { TasksPage } from "../pages/TasksPage";
import { TracePage } from "../pages/TracePage";
import { AppShell } from "./AppShell";
import { OperationsProvider } from "./OperationsProvider";
import { PreferencesProvider } from "./PreferencesProvider";

export function App() {
  return (
    <PreferencesProvider>
      <OperationsProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<OverviewPage />} />
              <Route path="plan" element={<PlanPage />} />
              <Route path="plans/:revisionId" element={<PlanPage />} />
              <Route path="inspection-tasks" element={<TasksPage />} />
              <Route path="trace" element={<TracePage />} />
              <Route path="trace/:traceId" element={<TracePage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </OperationsProvider>
    </PreferencesProvider>
  );
}
