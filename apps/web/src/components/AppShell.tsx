import {
  Activity,
  BookOpenCheck,
  ChevronRight,
  FileClock,
  FolderKanban,
  LogOut,
  Menu,
  Moon,
  Plus,
  Settings,
  ShieldCheck,
  Sun,
  X,
} from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuthStore } from "../auth/store";
import { useUiStore } from "../stores/ui";
import { Logo } from "./Logo";
import { Badge, Button, cx } from "./ui";

const links = [
  { to: "/", label: "Overview", icon: Activity, end: true },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/analyses", label: "Analyses", icon: BookOpenCheck },
  { to: "/audit", label: "Audit log", icon: FileClock },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppShell() {
  const user = useAuthStore((state) => state.user);
  const clearSession = useAuthStore((state) => state.clearSession);
  const { theme, setTheme, sidebarOpen, setSidebarOpen, toggleSidebar } = useUiStore();
  const location = useLocation();
  const navigate = useNavigate();
  const projectId = location.pathname.match(/^\/projects\/([^/]+)$/)?.[1];
  const newAnalysisTarget = projectId
    ? `/analyses/new?project=${encodeURIComponent(projectId)}`
    : "/analyses/new";

  useEffect(() => setSidebarOpen(false), [location.pathname, setSidebarOpen]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const resolved = theme === "system" ? (media.matches ? "dark" : "light") : theme;
      document.documentElement.dataset.theme = resolved;
      document.documentElement.style.colorScheme = resolved;
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);

  const logout = () => {
    clearSession();
    void navigate("/login", { replace: true });
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      {sidebarOpen ? (
        <button
          className="sidebar-scrim"
          onClick={() => setSidebarOpen(false)}
          aria-label="Close navigation"
        />
      ) : null}
      <aside className={cx("sidebar", sidebarOpen && "sidebar--open")} aria-label="Main navigation">
        <div className="sidebar__brand-row">
          <Logo />
          <button
            className="icon-button sidebar__close"
            onClick={toggleSidebar}
            aria-label="Close menu"
          >
            <X size={18} />
          </button>
        </div>

        <div className="workspace-chip">
          <span className="workspace-chip__mark">
            {user?.display_name?.slice(0, 1).toUpperCase() ?? "P"}
          </span>
          <span>
            <small>Workspace</small>
            <strong>{user?.display_name ?? "ProofStack"}</strong>
          </span>
          <ChevronRight size={15} aria-hidden="true" />
        </div>

        <nav className="sidebar__nav">
          <p>Workspace</p>
          {links.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => cx("nav-link", isActive && "nav-link--active")}
            >
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__assurance glass-card">
          <ShieldCheck size={20} aria-hidden="true" />
          <strong>Evidence boundary</strong>
          <p>Secrets stay redacted across findings, logs, and exported bundles.</p>
        </div>

        <div className="sidebar__user">
          <span className="avatar">{user?.display_name?.slice(0, 1).toUpperCase() ?? "U"}</span>
          <span>
            <strong>{user?.display_name ?? "Signed-in user"}</strong>
            <small>{user?.email}</small>
          </span>
          <button className="icon-button" aria-label="Sign out" title="Sign out" onClick={logout}>
            <LogOut size={17} />
          </button>
        </div>
      </aside>

      <div className="shell-content">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            onClick={toggleSidebar}
            aria-label="Open menu"
          >
            <Menu size={19} />
          </button>
          <div className="topbar__context">
            <span className="signal-dot" />
            <span>Acceptance workspace</span>
          </div>
          <div className="topbar__actions">
            {user?.role ? <Badge tone="neutral">{user.role}</Badge> : null}
            <button
              className="icon-button"
              aria-label={theme === "dark" ? "Use light theme" : "Use dark theme"}
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <Button size="sm" onClick={() => void navigate(newAnalysisTarget)}>
              <Plus size={16} />
              New analysis
            </Button>
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function AuthLayout({ children }: { children: ReactNode }) {
  const { theme, setTheme } = useUiStore();

  useEffect(() => {
    const resolved =
      theme === "system"
        ? window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : theme;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.style.colorScheme = resolved;
  }, [theme]);

  return (
    <div className="auth-shell">
      <div className="auth-shell__top">
        <Logo />
        <button
          className="icon-button"
          aria-label="Toggle color theme"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
        </button>
      </div>
      {children}
    </div>
  );
}
