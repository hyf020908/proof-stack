import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  FileArchive,
  FileDiff,
  FlaskConical,
  Github,
  ListChecks,
  Play,
  ServerCog,
  ShieldCheck,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { Button, Card, ErrorState, LoadingState, PageHeader, cx } from "../components/ui";

type SourceType = "demo" | "upload" | "github";

interface WizardState {
  projectId: string;
  sourceType: SourceType;
  githubUrl: string;
  archive: File | null;
  diff: File | null;
  requirements: string;
  acceptanceCriteria: string;
  policy: string;
  runner: "native" | "docker";
  validationCommands: string;
  installDependencies: boolean;
}

const steps = ["Select source", "Add requirements", "Configure validation", "Review and run"];

export function NewAnalysisPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<WizardState>({
    projectId: searchParams.get("project") ?? "",
    sourceType: "demo",
    githubUrl: "",
    archive: null,
    diff: null,
    requirements: "",
    acceptanceCriteria: "",
    policy: "default",
    runner: "native",
    validationCommands: "python -m compileall .\npytest -q",
    installDependencies: false,
  });
  const projects = useQuery({
    queryKey: ["projects", "wizard"],
    queryFn: () => api.projects.list({ page_size: 100 }),
  });
  const policies = useQuery({ queryKey: ["policies"], queryFn: api.policies.list });

  const selectedProject = projects.data?.items.find((project) => project.id === state.projectId);
  const commandList = useMemo(
    () =>
      state.validationCommands
        .split("\n")
        .map((command) => command.trim())
        .filter(Boolean),
    [state.validationCommands],
  );

  const start = useMutation({
    mutationFn: async () => {
      const common = {
        requirements: state.requirements,
        acceptance_criteria: state.acceptanceCriteria,
        policy: state.policy,
        runner: state.runner,
        validation_commands: commandList,
        install_dependencies: state.installDependencies,
      };
      if (state.sourceType === "demo") return api.analyses.startDemo(state.projectId, common);
      if (state.sourceType === "github") {
        return api.analyses.startGitHub(state.projectId, {
          ...common,
          repository_url: state.githubUrl,
        });
      }
      const form = new FormData();
      if (state.archive) form.append("source", state.archive);
      if (state.diff) form.append("diff", state.diff);
      form.append(
        "requirements",
        [
          state.requirements,
          state.acceptanceCriteria && `Acceptance criteria:\n${state.acceptanceCriteria}`,
        ]
          .filter(Boolean)
          .join("\n\n"),
      );
      form.append("policy_name", state.policy);
      form.append("runner", state.runner);
      form.append("validation_commands", JSON.stringify(commandList));
      return api.analyses.startUpload(state.projectId, form);
    },
    onSuccess: (analysis) => void navigate(`/analyses/${analysis.id}/progress`),
  });

  const validateStep = () => {
    setError(null);
    if (step === 0) {
      if (!state.projectId)
        return (setError("Select the project that should own this analysis."), false);
      if (
        state.sourceType === "github" &&
        !/^https:\/\/github\.com\/[^/]+\/[^/]+/.test(state.githubUrl)
      ) {
        return (setError("Enter a valid public GitHub repository or pull request URL."), false);
      }
      if (state.sourceType === "upload" && !state.archive) {
        return (setError("Choose a source ZIP archive. A diff remains optional."), false);
      }
    }
    if (step === 2 && commandList.length === 0) {
      return (
        setError("Add at least one validation command, or return to the runner configuration."),
        false
      );
    }
    return true;
  };

  const next = () => {
    if (validateStep()) setStep((current) => Math.min(3, current + 1));
  };

  if (projects.isLoading) return <LoadingState label="Preparing the analysis wizard…" />;
  if (projects.isError)
    return <ErrorState error={projects.error} retry={() => void projects.refetch()} />;

  return (
    <div className="page-stack wizard-page">
      <PageHeader
        eyebrow="New acceptance run"
        title="Build the evidence plan"
        description="Choose the source and the proof your team expects before merge."
      />
      <ol className="stepper" aria-label="Analysis setup progress">
        {steps.map((label, index) => (
          <li
            key={label}
            className={cx(index === step && "stepper__current", index < step && "stepper__done")}
            aria-current={index === step ? "step" : undefined}
          >
            <span>{index < step ? <Check size={14} /> : index + 1}</span>
            <strong>{label}</strong>
          </li>
        ))}
      </ol>

      <Card className="wizard-card">
        {step === 0 ? (
          <SourceStep state={state} setState={setState} projects={projects.data?.items ?? []} />
        ) : null}
        {step === 1 ? <RequirementsStep state={state} setState={setState} /> : null}
        {step === 2 ? (
          <ValidationStep
            state={state}
            setState={setState}
            policies={policies.data?.items.map((item) => item.name) ?? ["default"]}
          />
        ) : null}
        {step === 3 ? (
          <ReviewStep
            state={state}
            projectName={selectedProject?.name ?? "Unknown project"}
            commands={commandList}
          />
        ) : null}
        {error ? (
          <div className="form-error" role="alert">
            {error}
          </div>
        ) : null}
        {start.error ? (
          <div className="form-error" role="alert">
            {start.error.message}
          </div>
        ) : null}
        <footer className="wizard-actions">
          <Button
            variant="ghost"
            disabled={step === 0}
            onClick={() => {
              setError(null);
              setStep((current) => Math.max(0, current - 1));
            }}
          >
            <ArrowLeft size={16} /> Back
          </Button>
          {step < 3 ? (
            <Button onClick={next}>
              Continue <ArrowRight size={16} />
            </Button>
          ) : (
            <Button
              loading={start.isPending}
              onClick={() => {
                if (validateStep()) start.mutate();
              }}
            >
              <Play size={16} /> Run analysis
            </Button>
          )}
        </footer>
      </Card>
    </div>
  );
}

function SourceStep({
  state,
  setState,
  projects,
}: {
  state: WizardState;
  setState: (state: WizardState) => void;
  projects: Array<{ id: string; name: string }>;
}) {
  return (
    <section className="wizard-section">
      <div className="wizard-heading">
        <span>
          <FileArchive size={20} />
        </span>
        <div>
          <h2>Select the evidence source</h2>
          <p>Source material is handled under configured size, path, and timeout limits.</p>
        </div>
      </div>
      <label className="field">
        <span>Project</span>
        <select
          value={state.projectId}
          onChange={(event) => setState({ ...state, projectId: event.target.value })}
        >
          <option value="">Select a project</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
      </label>
      <div className="source-grid" role="radiogroup" aria-label="Source type">
        {(
          [
            {
              value: "demo",
              title: "Built-in demo",
              description: "Run the real pipeline on the maintained sample change.",
              icon: FlaskConical,
            },
            {
              value: "upload",
              title: "ZIP + diff",
              description: "Upload a source archive and optional unified diff or patch.",
              icon: FileDiff,
            },
            {
              value: "github",
              title: "Public GitHub",
              description: "Analyze a public repository or pull request URL.",
              icon: Github,
            },
          ] as const
        ).map(({ value, title, description, icon: Icon }) => (
          <button
            type="button"
            role="radio"
            aria-checked={state.sourceType === value}
            className={cx("source-option", state.sourceType === value && "source-option--selected")}
            key={value}
            onClick={() => setState({ ...state, sourceType: value })}
          >
            <Icon size={21} />
            <strong>{title}</strong>
            <span>{description}</span>
            {state.sourceType === value ? (
              <Check size={16} className="source-option__check" />
            ) : null}
          </button>
        ))}
      </div>
      {state.sourceType === "github" ? (
        <label className="field">
          <span>GitHub URL</span>
          <input
            type="url"
            value={state.githubUrl}
            onChange={(event) => setState({ ...state, githubUrl: event.target.value })}
            placeholder="https://github.com/owner/repository/pull/123"
          />
          <small className="field-hint">
            Public repositories work without a token; configured tokens improve rate limits.
          </small>
        </label>
      ) : null}
      {state.sourceType === "upload" ? (
        <div className="upload-grid">
          <label className="file-drop">
            <FileArchive size={24} />
            <strong>{state.archive?.name ?? "Choose source ZIP"}</strong>
            <span>Required · server upload limits apply</span>
            <input
              type="file"
              accept=".zip,application/zip"
              onChange={(event) => setState({ ...state, archive: event.target.files?.[0] ?? null })}
            />
          </label>
          <label className="file-drop">
            <FileDiff size={24} />
            <strong>{state.diff?.name ?? "Choose diff or patch"}</strong>
            <span>Optional · unified diff format</span>
            <input
              type="file"
              accept=".diff,.patch,text/x-diff,text/plain"
              onChange={(event) => setState({ ...state, diff: event.target.files?.[0] ?? null })}
            />
          </label>
        </div>
      ) : null}
    </section>
  );
}

function RequirementsStep({
  state,
  setState,
}: {
  state: WizardState;
  setState: (state: WizardState) => void;
}) {
  return (
    <section className="wizard-section">
      <div className="wizard-heading">
        <span>
          <ListChecks size={20} />
        </span>
        <div>
          <h2>Describe the intended change</h2>
          <p>Deterministic mapping links words, paths, symbols, routes, and tests to evidence.</p>
        </div>
      </div>
      <label className="field">
        <span>
          Requirement or user story <em>optional</em>
        </span>
        <textarea
          rows={8}
          value={state.requirements}
          onChange={(event) => setState({ ...state, requirements: event.target.value })}
          placeholder="As an API client, I need…&#10;&#10;Include issue context, expected behavior, or Markdown."
        />
        <small className="field-hint">
          No external model is required. The offline mapper remains available by default.
        </small>
      </label>
      <label className="field">
        <span>
          Acceptance criteria <em>one per line</em>
        </span>
        <textarea
          rows={6}
          value={state.acceptanceCriteria}
          onChange={(event) => setState({ ...state, acceptanceCriteria: event.target.value })}
          placeholder="The endpoint rejects an invalid payload&#10;The response schema remains compatible&#10;Integration tests cover authorization"
        />
      </label>
    </section>
  );
}

function ValidationStep({
  state,
  setState,
  policies,
}: {
  state: WizardState;
  setState: (state: WizardState) => void;
  policies: string[];
}) {
  return (
    <section className="wizard-section">
      <div className="wizard-heading">
        <span>
          <ServerCog size={20} />
        </span>
        <div>
          <h2>Configure isolated validation</h2>
          <p>
            Only server-approved command arrays can execute. Skipped and unavailable remain
            explicit.
          </p>
        </div>
      </div>
      <div className="field-row">
        <label className="field">
          <span>Policy</span>
          <select
            value={state.policy}
            onChange={(event) => setState({ ...state, policy: event.target.value })}
          >
            {Array.from(new Set(["default", ...policies])).map((policy) => (
              <option key={policy} value={policy}>
                {policy}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Runner</span>
          <select
            value={state.runner}
            onChange={(event) =>
              setState({ ...state, runner: event.target.value as WizardState["runner"] })
            }
          >
            <option value="native">Native safe runner</option>
            <option value="docker">Docker sandbox</option>
          </select>
        </label>
      </div>
      <label className="field">
        <span>
          Validation commands <em>one allowlisted command per line</em>
        </span>
        <textarea
          className="code-input"
          rows={7}
          value={state.validationCommands}
          onChange={(event) => setState({ ...state, validationCommands: event.target.value })}
        />
      </label>
      <label className="check-field">
        <input
          type="checkbox"
          checked={state.installDependencies}
          onChange={(event) => setState({ ...state, installDependencies: event.target.checked })}
        />
        <span>
          <strong>Allow dependency installation</strong>
          <small>
            Disabled by default. The configured runner applies network and resource controls.
          </small>
        </span>
      </label>
      {state.runner === "docker" ? (
        <div className="notice">
          <ShieldCheck size={18} />
          <p>
            Docker sandbox availability is checked by the server. Network access, privileged mode,
            and Docker socket mounting remain disabled by default.
          </p>
        </div>
      ) : null}
    </section>
  );
}

function ReviewStep({
  state,
  projectName,
  commands,
}: {
  state: WizardState;
  projectName: string;
  commands: string[];
}) {
  return (
    <section className="wizard-section">
      <div className="wizard-heading">
        <span>
          <ShieldCheck size={20} />
        </span>
        <div>
          <h2>Review the evidence plan</h2>
          <p>The run can be cancelled while active. Every stage transition is auditable.</p>
        </div>
      </div>
      <div className="review-grid">
        <div>
          <small>Project</small>
          <strong>{projectName}</strong>
        </div>
        <div>
          <small>Source</small>
          <strong>
            {state.sourceType === "upload"
              ? state.archive?.name
              : state.sourceType === "github"
                ? state.githubUrl
                : "ProofStack demo repository"}
          </strong>
        </div>
        <div>
          <small>Policy</small>
          <strong>{state.policy}</strong>
        </div>
        <div>
          <small>Runner</small>
          <strong>{state.runner === "native" ? "Native safe runner" : "Docker sandbox"}</strong>
        </div>
        <div>
          <small>Requirements</small>
          <strong>{state.requirements.trim() ? "Provided" : "No explicit requirement"}</strong>
        </div>
        <div>
          <small>Validation</small>
          <strong>
            {commands.length} command{commands.length === 1 ? "" : "s"}
          </strong>
        </div>
      </div>
      <div className="command-review">
        <h3>Validation plan</h3>
        {commands.map((command) => (
          <code key={command}>{command}</code>
        ))}
      </div>
      <div className="notice notice--accent">
        <ShieldCheck size={18} />
        <p>
          Starting this run records an audit event and sends the selected source to your configured
          ProofStack API. Secrets are redacted from findings and bundles.
        </p>
      </div>
    </section>
  );
}
