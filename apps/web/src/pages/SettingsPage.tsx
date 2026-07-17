import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  CircleOff,
  Github,
  KeyRound,
  Moon,
  ServerCog,
  ShieldCheck,
  Sun,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import { useAuthStore } from "../auth/store";
import { useUiStore } from "../stores/ui";
import { Badge, Button, Card, ErrorState, LoadingState, PageHeader, cx } from "../components/ui";

export function SettingsPage() {
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const { theme, setTheme } = useUiStore();
  const organization = useQuery({ queryKey: ["organization"], queryFn: api.organization.current });
  const members = useQuery({
    queryKey: ["organization", "members"],
    queryFn: api.organization.members,
  });
  const config = useQuery({ queryKey: ["system", "config"], queryFn: api.system.config });
  const version = useQuery({ queryKey: ["system", "version"], queryFn: api.system.version });
  const [name, setName] = useState("");
  useEffect(() => setName(organization.data?.name ?? ""), [organization.data?.name]);
  const save = useMutation({
    mutationFn: () => api.organization.update({ name }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["organization"] }),
  });

  if (organization.isLoading) return <LoadingState label="Loading workspace settings…" />;
  if (organization.isError)
    return <ErrorState error={organization.error} retry={() => void organization.refetch()} />;
  const canEdit = user?.role === "owner";
  const system = config.data;

  return (
    <div className="page-stack settings-page">
      <PageHeader
        eyebrow="Workspace controls"
        title="Settings"
        description="Safe public configuration, organization identity, and interface preferences."
      />
      <div className="settings-grid">
        <Card className="settings-card settings-card--wide">
          <div className="settings-card__head">
            <span>
              <Users size={19} />
            </span>
            <div>
              <h2>Organization</h2>
              <p>Visible to members of this tenant only.</p>
            </div>
          </div>
          <div className="settings-form">
            <label className="field">
              <span>Organization name</span>
              <input
                value={name}
                disabled={!canEdit}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Slug</span>
              <input value={organization.data?.slug ?? ""} disabled />
            </label>
            <Button
              disabled={!canEdit || name.trim().length < 2 || name === organization.data?.name}
              loading={save.isPending}
              onClick={() => save.mutate()}
            >
              Save organization
            </Button>
          </div>
          {!canEdit ? (
            <p className="permission-note">
              <KeyRound size={15} /> Only owners can edit organization settings.
            </p>
          ) : null}
          {save.isSuccess ? (
            <p className="success-note">
              <CheckCircle2 size={15} /> Organization saved.
            </p>
          ) : null}
          {save.error ? <div className="form-error">{save.error.message}</div> : null}
        </Card>

        <Card className="settings-card">
          <div className="settings-card__head">
            <span>
              <Sun size={19} />
            </span>
            <div>
              <h2>Appearance</h2>
              <p>Choose a balanced light or dark glass surface.</p>
            </div>
          </div>
          <div className="theme-picker">
            {(
              [
                { value: "light", label: "Light", icon: Sun },
                { value: "dark", label: "Dark", icon: Moon },
                { value: "system", label: "System", icon: ServerCog },
              ] as const
            ).map(({ value, label, icon: Icon }) => (
              <button
                className={cx(theme === value && "selected")}
                key={value}
                onClick={() => setTheme(value)}
              >
                <Icon size={18} />
                <span>{label}</span>
                {theme === value ? <CheckCircle2 size={14} /> : null}
              </button>
            ))}
          </div>
        </Card>

        <Card className="settings-card">
          <div className="settings-card__head">
            <span>
              <Users size={19} />
            </span>
            <div>
              <h2>Members</h2>
              <p>{members.data?.total ?? 0} organization accounts</p>
            </div>
          </div>
          <div className="member-list">
            {members.data?.items.slice(0, 6).map((member) => (
              <div key={member.id}>
                <span className="avatar">{member.display_name.slice(0, 1).toUpperCase()}</span>
                <span>
                  <strong>{member.display_name}</strong>
                  <small>{member.email}</small>
                </span>
                <Badge tone="neutral">{member.role}</Badge>
              </div>
            ))}
          </div>
        </Card>

        <Card className="settings-card settings-card--wide">
          <div className="settings-card__head">
            <span>
              <ShieldCheck size={19} />
            </span>
            <div>
              <h2>System capabilities</h2>
              <p>Only availability flags are exposed. Secret values never reach the browser.</p>
            </div>
          </div>
          {config.isError ? (
            <div className="form-error">
              Public system configuration is unavailable: {config.error.message}
            </div>
          ) : (
            <div className="capability-grid">
              <Capability
                icon={<ServerCog size={17} />}
                label="Task backend"
                value={system?.task_backend ?? "Unknown"}
                available
              />
              <Capability
                icon={<ServerCog size={17} />}
                label="Execution runner"
                value={system?.runner ?? "Unknown"}
                available={system?.runner_available !== false}
              />
              <Capability
                icon={<Github size={17} />}
                label="GitHub token"
                value={system?.github_token_configured ? "Configured" : "Not configured"}
                available={Boolean(system?.github_token_configured)}
              />
              <Capability
                icon={<ShieldCheck size={17} />}
                label="Semgrep"
                value={
                  system?.semgrep_enabled
                    ? system.semgrep_available === false
                      ? "Unavailable"
                      : "Enabled"
                    : "Disabled"
                }
                available={Boolean(system?.semgrep_enabled && system?.semgrep_available !== false)}
              />
              <Capability
                icon={<KeyRound size={17} />}
                label="Optional LLM"
                value={system?.llm_enabled ? "Enabled" : "Offline deterministic mode"}
                available={Boolean(system?.llm_enabled)}
              />
              <Capability
                icon={<CheckCircle2 size={17} />}
                label="Demo mode"
                value={system?.demo_mode ? "Enabled" : "Disabled"}
                available={Boolean(system?.demo_mode)}
              />
            </div>
          )}
        </Card>

        <Card className="settings-card settings-card--wide about-card">
          <div>
            <p className="eyebrow">About ProofStack</p>
            <h2>Version {system?.version ?? version.data?.version ?? "0.1.0"}</h2>
            <p>
              Evidence-driven acceptance for AI-generated code changes. Core analysis remains
              deterministic and works without external LLM credentials.
            </p>
          </div>
          <div>
            <Badge tone="neutral">{system?.environment ?? "local"}</Badge>
            <Badge tone={system?.demo_mode ? "warn" : "pass"}>
              {system?.demo_mode ? "demo mode" : "standard mode"}
            </Badge>
          </div>
        </Card>
      </div>
    </div>
  );
}

function Capability({
  icon,
  label,
  value,
  available,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  available: boolean;
}) {
  return (
    <div>
      <span>{icon}</span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
      </div>
      {available ? (
        <CheckCircle2 size={16} className="success-icon" />
      ) : (
        <CircleOff size={16} className="muted-icon" />
      )}
    </div>
  );
}
