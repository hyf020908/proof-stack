export type Identifier = string;
export type Role = "owner" | "maintainer" | "reviewer" | "viewer";
export type Verdict = "pass" | "warn" | "fail" | "unknown";
export type AnalysisStatus =
  | "queued"
  | "preparing"
  | "analyzing"
  | "testing"
  | "evaluating"
  | "completed"
  | "failed"
  | "cancelled";
export type Severity = "info" | "low" | "medium" | "high" | "critical";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages?: number;
}

export interface User {
  id: Identifier;
  organization_id: Identifier;
  email: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  created_at?: string;
}

export interface Organization {
  id: Identifier;
  name: string;
  slug: string;
  created_at?: string;
  updated_at?: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type?: string;
  expires_in?: number;
  user?: User;
}

export interface Project {
  id: Identifier;
  organization_id?: Identifier;
  name: string;
  slug: string;
  description: string;
  default_branch: string;
  repository_provider: string;
  repository_url: string | null;
  created_by?: Identifier;
  created_at: string;
  updated_at?: string;
  analyses_count?: number;
  latest_verdict?: Verdict;
}

export interface AnalysisRun {
  id: Identifier;
  project_id: Identifier;
  source_type: string;
  source_reference?: string | null;
  base_revision?: string | null;
  head_revision?: string | null;
  status: AnalysisStatus;
  verdict: Verdict;
  risk_score: number;
  progress: number;
  current_stage?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string;
  error_summary?: string | null;
  created_by?: Identifier;
  metrics?: AnalysisMetrics;
}

export interface AnalysisMetrics {
  changed_files?: number;
  additions?: number;
  deletions?: number;
  findings_total?: number;
  critical_findings?: number;
  high_findings?: number;
  requirement_coverage?: number;
  test_evidence_score?: number;
  validation_passed?: number;
  duration_ms?: number;
  [key: string]: number | undefined;
}

export interface ChangedFile {
  id: Identifier;
  analysis_run_id?: Identifier;
  path: string;
  change_type: string;
  additions: number;
  deletions: number;
  language?: string | null;
  risk_score: number;
  is_test: boolean;
  is_generated?: boolean;
  finding_count?: number;
  requirement_count?: number;
  test_count?: number;
}

export interface Finding {
  id: Identifier;
  analysis_run_id?: Identifier;
  category: string;
  severity: Severity;
  title: string;
  description: string;
  file_path?: string | null;
  start_line?: number | null;
  end_line?: number | null;
  rule_id?: string | null;
  remediation?: string | null;
  evidence?: unknown;
  fingerprint?: string;
  status: "open" | "acknowledged" | "resolved" | "false_positive";
}

export interface Requirement {
  id: Identifier;
  external_id?: string | null;
  title: string;
  description?: string;
  acceptance_criteria?: string | string[];
  source?: string;
  confidence: number;
  coverage_score?: number;
  supported?: boolean;
  changed_files?: Array<{ id?: Identifier; path: string }> | string[];
  changed_symbols?: Array<{ id?: Identifier; name?: string; qualified_name?: string }> | string[];
  tests?: Array<{ id?: Identifier; name?: string; qualified_name?: string }> | string[];
  evidence?: unknown;
}

export interface TestExecution {
  id: Identifier;
  command: string;
  status: "passed" | "failed" | "skipped" | "unavailable" | "timed_out";
  exit_code?: number | null;
  duration_ms: number;
  stdout_excerpt?: string | null;
  stderr_excerpt?: string | null;
  timed_out?: boolean;
  environment?: Record<string, unknown> | string;
  runner?: string;
}

export interface PolicyDecision {
  id: Identifier;
  policy_name: string;
  rule_id: string;
  outcome: "pass" | "warn" | "fail";
  explanation: string;
  observed_value?: unknown;
  expected_value?: unknown;
  operator?: string;
  evidence_references?: string[];
}

export interface GraphNode {
  id: string;
  label?: string;
  name?: string;
  type?: string;
  changed?: boolean;
  blast_radius?: boolean;
  risk_score?: number;
  file_path?: string;
  metadata?: Record<string, unknown>;
}

export interface GraphEdge {
  id?: string;
  source: string;
  target: string;
  edge_type?: string;
  type?: string;
  confidence?: number;
}

export interface ImpactGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated?: boolean;
  total_nodes?: number;
}

export interface AnalysisEvent {
  id?: Identifier;
  stage?: string;
  level?: string;
  message: string;
  status?: string;
  progress?: number;
  created_at?: string;
  timestamp?: string;
  duration_ms?: number;
}

export interface AnalysisProgress {
  analysis_id?: Identifier;
  status: AnalysisStatus;
  progress: number;
  current_stage?: string | null;
  stages?: Array<{
    name: string;
    status: string;
    started_at?: string | null;
    completed_at?: string | null;
    duration_ms?: number | null;
    message?: string | null;
  }>;
  error_summary?: string | null;
}

export interface EvidenceArtifact {
  id?: Identifier;
  artifact_type?: string;
  name: string;
  content_type: string;
  sha256: string;
  size: number;
  created_at?: string;
  verified?: boolean;
}

export interface EvidenceResponse {
  schema_version?: string;
  manifest?: Record<string, unknown>;
  artifacts: EvidenceArtifact[];
  verified?: boolean;
}

export interface AuditEvent {
  id: Identifier;
  organization_id?: Identifier;
  user_id?: Identifier | null;
  user?: { id?: Identifier; display_name?: string; email?: string } | null;
  action: string;
  resource_type: string;
  resource_id?: Identifier | null;
  metadata?: Record<string, unknown>;
  ip_address?: string | null;
  created_at: string;
}

export interface PublicSystemConfig {
  version: string;
  environment?: string;
  demo_mode: boolean;
  github_token_configured: boolean;
  runner: string;
  runner_available?: boolean;
  semgrep_enabled: boolean;
  semgrep_available?: boolean;
  task_backend?: string;
  llm_enabled?: boolean;
}

export interface ApiErrorShape {
  detail?: string | Array<{ loc?: Array<string | number>; msg: string }>;
  message?: string;
  error?: { code?: string; message?: string; details?: unknown } | string;
  request_id?: string;
}
