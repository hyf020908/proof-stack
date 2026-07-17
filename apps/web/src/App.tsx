import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { api } from "./api/client";
import { useAuthStore } from "./auth/store";
import { AppShell } from "./components/AppShell";
import { LoadingState } from "./components/ui";
import { AuthPage } from "./pages/AuthPage";

const DashboardPage = lazy(() =>
  import("./pages/DashboardPage").then((module) => ({ default: module.DashboardPage })),
);
const ProjectsPage = lazy(() =>
  import("./pages/ProjectsPage").then((module) => ({ default: module.ProjectsPage })),
);
const ProjectPage = lazy(() =>
  import("./pages/ProjectPage").then((module) => ({ default: module.ProjectPage })),
);
const AnalysesPage = lazy(() =>
  import("./pages/AnalysesPage").then((module) => ({ default: module.AnalysesPage })),
);
const NewAnalysisPage = lazy(() =>
  import("./pages/NewAnalysisPage").then((module) => ({ default: module.NewAnalysisPage })),
);
const AnalysisProgressPage = lazy(() =>
  import("./pages/AnalysisProgressPage").then((module) => ({
    default: module.AnalysisProgressPage,
  })),
);
const AnalysisPage = lazy(() =>
  import("./pages/AnalysisPage").then((module) => ({ default: module.AnalysisPage })),
);
const AuditPage = lazy(() =>
  import("./pages/AuditPage").then((module) => ({ default: module.AuditPage })),
);
const SettingsPage = lazy(() =>
  import("./pages/SettingsPage").then((module) => ({ default: module.SettingsPage })),
);
const NotFoundPage = lazy(() =>
  import("./pages/NotFoundPage").then((module) => ({ default: module.NotFoundPage })),
);
const OverviewTab = lazy(() =>
  import("./pages/analysis/OverviewTab").then((module) => ({ default: module.OverviewTab })),
);
const ChangedFilesTab = lazy(() =>
  import("./pages/analysis/ChangedFilesTab").then((module) => ({
    default: module.ChangedFilesTab,
  })),
);
const ImpactGraphTab = lazy(() =>
  import("./pages/analysis/ImpactGraphTab").then((module) => ({
    default: module.ImpactGraphTab,
  })),
);
const RequirementsTab = lazy(() =>
  import("./pages/analysis/RequirementsTab").then((module) => ({
    default: module.RequirementsTab,
  })),
);
const FindingsTab = lazy(() =>
  import("./pages/analysis/FindingsTab").then((module) => ({ default: module.FindingsTab })),
);
const ValidationTab = lazy(() =>
  import("./pages/analysis/ValidationTab").then((module) => ({
    default: module.ValidationTab,
  })),
);
const PoliciesTab = lazy(() =>
  import("./pages/analysis/PoliciesTab").then((module) => ({ default: module.PoliciesTab })),
);
const EvidenceTab = lazy(() =>
  import("./pages/analysis/EvidenceTab").then((module) => ({ default: module.EvidenceTab })),
);

function ProtectedLayout() {
  const location = useLocation();
  const accessToken = useAuthStore((state) => state.accessToken);
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const clearSession = useAuthStore((state) => state.clearSession);
  const me = useQuery({
    queryKey: ["auth", "me"],
    queryFn: api.auth.me,
    enabled: Boolean(accessToken && !user),
    retry: false,
  });

  useEffect(() => {
    if (me.data && !user) setUser(me.data);
  }, [me.data, setUser, user]);

  if (!accessToken) return <Navigate to="/login" state={{ from: location }} replace />;
  if (!user && me.isLoading)
    return (
      <div className="route-loading">
        <LoadingState label="Restoring your evidence workspace…" />
      </div>
    );
  if (me.isError) {
    clearSession();
    return <Navigate to="/login" replace />;
  }
  return <AppShell />;
}

export function App() {
  return (
    <Suspense fallback={<LoadingState label="Opening the evidence view…" />}>
      <Routes>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/register" element={<AuthPage mode="register" />} />
        <Route element={<ProtectedLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="projects/:projectId" element={<ProjectPage />} />
          <Route path="analyses" element={<AnalysesPage />} />
          <Route path="analyses/new" element={<NewAnalysisPage />} />
          <Route path="analyses/:analysisId/progress" element={<AnalysisProgressPage />} />
          <Route path="analyses/:analysisId" element={<AnalysisPage />}>
            <Route index element={<OverviewTab />} />
            <Route path="files" element={<ChangedFilesTab />} />
            <Route path="graph" element={<ImpactGraphTab />} />
            <Route path="requirements" element={<RequirementsTab />} />
            <Route path="findings" element={<FindingsTab />} />
            <Route path="validation" element={<ValidationTab />} />
            <Route path="policies" element={<PoliciesTab />} />
            <Route path="evidence" element={<EvidenceTab />} />
          </Route>
          <Route path="audit" element={<AuditPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
