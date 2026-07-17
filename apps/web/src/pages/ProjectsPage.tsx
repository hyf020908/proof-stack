import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  FolderKanban,
  GitBranch,
  MoreHorizontal,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";

import { api } from "../api/client";
import type { Project } from "../api/types";
import { canManageProjects, useAuthStore } from "../auth/store";
import { formatDate } from "../components/format";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
  PageHeader,
  VerdictBadge,
} from "../components/ui";

const projectSchema = z.object({
  name: z.string().trim().min(2, "Project name must contain at least 2 characters.").max(100),
  slug: z
    .string()
    .trim()
    .max(80)
    .regex(/^$|^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Use lowercase letters, numbers, and hyphens."),
  description: z.string().trim().max(500),
  default_branch: z.string().trim().min(1, "Enter a default branch.").max(120),
  repository_provider: z.enum(["local", "github", "other"]),
  repository_url: z
    .string()
    .trim()
    .refine((value) => !value || /^https?:\/\//.test(value), "Use a valid HTTP or HTTPS URL."),
});

type ProjectFields = z.infer<typeof projectSchema>;

const defaults: ProjectFields = {
  name: "",
  slug: "",
  description: "",
  default_branch: "main",
  repository_provider: "local",
  repository_url: "",
};

export function ProjectsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const role = useAuthStore((state) => state.user?.role);
  const allowed = canManageProjects(role);
  const [search, setSearch] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const query = useQuery({
    queryKey: ["projects", search],
    queryFn: () => api.projects.list({ page_size: 100, search }),
  });

  const form = useForm<ProjectFields>({
    resolver: zodResolver(projectSchema),
    defaultValues: defaults,
  });
  const save = useMutation({
    mutationFn: (values: ProjectFields) => {
      const input = {
        ...values,
        slug: values.slug || undefined,
        repository_url: values.repository_url || null,
      };
      return editing ? api.projects.update(editing.id, input) : api.projects.create(input);
    },
    onSuccess: (project) => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      setEditorOpen(false);
      setEditing(null);
      if (!editing) void navigate(`/projects/${project.id}`);
    },
  });

  const remove = useMutation({
    mutationFn: (project: Project) => api.projects.remove(project.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      setDeleting(null);
    },
  });

  const openCreate = () => {
    form.reset(defaults);
    setEditing(null);
    setEditorOpen(true);
  };

  const openEdit = (project: Project) => {
    form.reset({
      name: project.name,
      slug: project.slug,
      description: project.description ?? "",
      default_branch: project.default_branch ?? "main",
      repository_provider: ["local", "github", "other"].includes(project.repository_provider)
        ? (project.repository_provider as ProjectFields["repository_provider"])
        : "other",
      repository_url: project.repository_url ?? "",
    });
    setEditing(project);
    setEditorOpen(true);
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Repository scopes"
        title="Projects"
        description="Keep analyses, policies, and audit history organized around a codebase."
        actions={
          allowed ? (
            <Button onClick={openCreate}>
              <Plus size={16} /> New project
            </Button>
          ) : undefined
        }
      />
      <Card className="toolbar-card">
        <label className="search-field">
          <Search size={17} aria-hidden="true" />
          <span className="sr-only">Search projects</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by name or repository…"
          />
        </label>
        <span className="result-count">{query.data?.total ?? 0} projects</span>
      </Card>

      {query.isLoading ? <LoadingState label="Loading projects…" /> : null}
      {query.isError ? <ErrorState error={query.error} retry={() => void query.refetch()} /> : null}
      {query.isSuccess && !query.data.items.length ? (
        <EmptyState
          icon={<FolderKanban />}
          title={search ? "No projects found" : "Create an evidence scope"}
          description={
            search
              ? "Try a different search term."
              : allowed
                ? "A project groups its source, analyses, and acceptance history."
                : "A maintainer can create the first project for this organization."
          }
          action={
            !search && allowed ? <Button onClick={openCreate}>Create project</Button> : undefined
          }
        />
      ) : null}

      <section className="project-grid">
        {query.data?.items.map((project) => (
          <Card className="project-card" key={project.id}>
            <div className="project-card__top">
              <span className="project-icon">
                <FolderKanban size={20} />
              </span>
              {allowed ? (
                <div className="menu-wrap">
                  <button
                    className="icon-button"
                    aria-label={`Project actions for ${project.name}`}
                  >
                    <MoreHorizontal size={18} />
                  </button>
                  <div className="hover-menu">
                    <button onClick={() => openEdit(project)}>Edit project</button>
                    <button className="danger-text" onClick={() => setDeleting(project)}>
                      <Trash2 size={14} /> Delete project
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
            <div className="project-card__body">
              <Link to={`/projects/${project.id}`}>
                <h2>{project.name}</h2>
              </Link>
              <p>{project.description || "No project description provided."}</p>
            </div>
            <div className="project-meta">
              <span>
                <GitBranch size={14} />
                {project.default_branch}
              </span>
              <span>{project.repository_provider}</span>
            </div>
            {project.repository_url ? (
              <a
                className="repository-link"
                href={project.repository_url}
                target="_blank"
                rel="noreferrer"
              >
                {project.repository_url.replace(/^https?:\/\//, "")}
                <ArrowUpRight size={14} />
              </a>
            ) : (
              <span className="repository-link repository-link--muted">
                Local or uploaded sources
              </span>
            )}
            <div className="project-card__footer">
              <div>
                <small>Latest verdict</small>
                <VerdictBadge verdict={project.latest_verdict ?? "unknown"} />
              </div>
              <div>
                <small>Analyses</small>
                <strong>{project.analyses_count ?? 0}</strong>
              </div>
              <div>
                <small>Updated</small>
                <span>{formatDate(project.updated_at ?? project.created_at)}</span>
              </div>
            </div>
          </Card>
        ))}
      </section>

      <Modal
        open={editorOpen}
        title={editing ? "Edit project" : "Create a project"}
        description="Repository metadata helps ProofStack explain source context."
        onClose={() => setEditorOpen(false)}
      >
        <form
          className="form-stack"
          onSubmit={(event) => void form.handleSubmit((values) => save.mutate(values))(event)}
          noValidate
        >
          <div className="field-row">
            <label className="field">
              <span>Name</span>
              <input autoFocus {...form.register("name")} />
              {form.formState.errors.name ? (
                <small role="alert">{form.formState.errors.name.message}</small>
              ) : null}
            </label>
            <label className="field">
              <span>
                Slug <em>optional</em>
              </span>
              <input placeholder="generated-from-name" {...form.register("slug")} />
              {form.formState.errors.slug ? (
                <small role="alert">{form.formState.errors.slug.message}</small>
              ) : null}
            </label>
          </div>
          <label className="field">
            <span>Description</span>
            <textarea rows={3} {...form.register("description")} />
            {form.formState.errors.description ? (
              <small role="alert">{form.formState.errors.description.message}</small>
            ) : null}
          </label>
          <div className="field-row">
            <label className="field">
              <span>Default branch</span>
              <input {...form.register("default_branch")} />
              {form.formState.errors.default_branch ? (
                <small role="alert">{form.formState.errors.default_branch.message}</small>
              ) : null}
            </label>
            <label className="field">
              <span>Provider</span>
              <select {...form.register("repository_provider")}>
                <option value="local">Local / upload</option>
                <option value="github">GitHub</option>
                <option value="other">Other</option>
              </select>
            </label>
          </div>
          <label className="field">
            <span>
              Repository URL <em>optional</em>
            </span>
            <input
              type="url"
              placeholder="https://github.com/owner/repository"
              {...form.register("repository_url")}
            />
            {form.formState.errors.repository_url ? (
              <small role="alert">{form.formState.errors.repository_url.message}</small>
            ) : null}
          </label>
          {save.error ? (
            <div className="form-error" role="alert">
              {save.error.message}
            </div>
          ) : null}
          <div className="modal-actions">
            <Button type="button" variant="ghost" onClick={() => setEditorOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              {editing ? "Save changes" : "Create project"}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={Boolean(deleting)}
        title="Delete this project?"
        description="Its analyses, findings, and evidence records will be permanently removed according to the server retention policy."
        onClose={() => setDeleting(null)}
      >
        <div className="confirm-body">
          <p>
            Type-free confirmation for <strong>{deleting?.name}</strong>. This action cannot be
            undone.
          </p>
          {remove.error ? (
            <div className="form-error" role="alert">
              {remove.error.message}
            </div>
          ) : null}
          <div className="modal-actions">
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              Keep project
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() => deleting && remove.mutate(deleting)}
            >
              Delete project
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
