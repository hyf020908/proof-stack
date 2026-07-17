"""Self-contained Markdown and HTML rendering for evidence bundles."""

from __future__ import annotations

import html
from collections.abc import Mapping
from typing import Any


def _mapping_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return default


def _sequence(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_markdown(value: Any) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def build_summary(payload: Mapping[str, Any], generated_at: str) -> str:
    """Render a concise evidence summary for source review and terminals."""

    analysis = payload["analysis"]
    analysis_id = _mapping_value(analysis, "id", _mapping_value(analysis, "analysis_id", "unknown"))
    verdict = _mapping_value(analysis, "verdict", "unknown")
    risk = _mapping_value(analysis, "risk_score", None)
    if risk is None:
        risk = _mapping_value(_mapping_value(analysis, "risk", {}), "score", "unknown")
    findings = _sequence(payload["findings"])
    tests = _sequence(payload["test_results"])
    policies = _sequence(payload["policy_decisions"])
    changed_files = _sequence(payload["changed_files"])

    severity_counts: dict[str, int] = {}
    for finding in findings:
        severity = str(_mapping_value(finding, "severity", "unknown"))
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    passed_tests = sum(_mapping_value(test, "status") == "passed" for test in tests)

    lines = [
        "# ProofStack Evidence Summary",
        "",
        f"- Analysis: `{_safe_markdown(analysis_id)}`",
        f"- Generated: `{generated_at}`",
        f"- Verdict: **{_safe_markdown(str(verdict).upper())}**",
        f"- Risk score: **{_safe_markdown(risk)}/100**",
        f"- Changed files: **{len(changed_files)}**",
        f"- Findings: **{len(findings)}**",
        f"- Passing validations: **{passed_tests}/{len(tests)}**",
        f"- Policy decisions: **{len(policies)}**",
        "",
        "## Finding severity",
        "",
    ]
    if severity_counts:
        lines.extend(
            f"- {severity.title()}: {count}" for severity, count in sorted(severity_counts.items())
        )
    else:
        lines.append("No findings were recorded.")
    lines.extend(["", "## Key findings", ""])
    if findings:
        for finding in findings[:10]:
            severity = _safe_markdown(_mapping_value(finding, "severity", "unknown"))
            title = _safe_markdown(_mapping_value(finding, "title", "Untitled finding"))
            lines.append(f"- **{severity.upper()}** — {title}")
    else:
        lines.append("No findings were recorded.")
    lines.extend(
        [
            "",
            "## Verification",
            "",
            (
                "Run `proofstack evidence verify <bundle-directory-or-zip>` before relying "
                "on this bundle."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def build_report(payload: Mapping[str, Any], generated_at: str, schema_version: str) -> str:
    """Render an offline HTML report with no scripts or external resources."""

    analysis = payload["analysis"]
    verdict = str(_mapping_value(analysis, "verdict", "unknown"))
    risk = _mapping_value(analysis, "risk_score", None)
    if risk is None:
        risk = _mapping_value(_mapping_value(analysis, "risk", {}), "score", "unknown")
    findings = _sequence(payload["findings"])
    tests = _sequence(payload["test_results"])
    policies = _sequence(payload["policy_decisions"])
    offline_notice = (
        f"Generated {generated_at}. This report is self-contained and requires no network access."
    )

    finding_rows = (
        "".join(
            "<tr>"
            f"<td>{html.escape(str(_mapping_value(item, 'severity', 'unknown')))}</td>"
            f"<td>{html.escape(str(_mapping_value(item, 'category', 'unknown')))}</td>"
            f"<td>{html.escape(str(_mapping_value(item, 'title', 'Untitled finding')))}</td>"
            f"<td>{html.escape(str(_mapping_value(item, 'file_path', '—')))}</td>"
            "</tr>"
            for item in findings[:200]
        )
        or '<tr><td colspan="4">No findings were recorded.</td></tr>'
    )
    test_rows = (
        "".join(
            "<tr>"
            f"<td>{html.escape(str(_mapping_value(item, 'command', '—')))}</td>"
            f"<td>{html.escape(str(_mapping_value(item, 'status', 'unknown')))}</td>"
            f"<td>{html.escape(str(_mapping_value(item, 'duration_ms', '—')))}</td>"
            "</tr>"
            for item in tests[:200]
        )
        or '<tr><td colspan="3">No validation results were recorded.</td></tr>'
    )
    policy_rows = (
        "".join(
            "<tr>"
            f"<td>{html.escape(str(_mapping_value(item, 'rule_id', '—')))}</td>"
            f"<td>{html.escape(str(_mapping_value(item, 'outcome', 'unknown')))}</td>"
            f"<td>{html.escape(str(_mapping_value(item, 'explanation', '—')))}</td>"
            "</tr>"
            for item in policies[:200]
        )
        or '<tr><td colspan="3">No policy decisions were recorded.</td></tr>'
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy"
    content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
  <title>ProofStack Evidence Report</title>
  <style>
    :root {{ color-scheme: light dark; font-family: ui-serif, Georgia, serif; }}
    body {{ max-width: 1100px; margin: 0 auto; padding: 2rem; line-height: 1.5; }}
    header, section {{ border: 1px solid #d8d2ce; border-radius: 12px;
      padding: 1.25rem; margin: 1rem 0; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: .75rem; }}
    .metric {{ background: rgba(235, 95, 64, .08); border-radius: 8px; padding: 1rem; }}
    table {{ width: 100%; border-collapse: collapse;
      font-family: ui-sans-serif, system-ui, sans-serif; }}
    th, td {{ border-bottom: 1px solid #d8d2ce; padding: .65rem;
      text-align: left; vertical-align: top; }}
    th {{ font-weight: 650; }}
    .label {{ color: #b5472d; text-transform: uppercase; font-size: .8rem; letter-spacing: .06em; }}
  </style>
</head>
<body>
  <header>
    <p class="label">ProofStack evidence bundle · schema {html.escape(schema_version)}</p>
    <h1>Acceptance evidence report</h1>
    <p>{html.escape(offline_notice)}</p>
    <div class="metrics">
      <div class="metric"><strong>Verdict</strong><br>{html.escape(verdict.upper())}</div>
      <div class="metric"><strong>Risk</strong><br>{html.escape(str(risk))}/100</div>
      <div class="metric"><strong>Findings</strong><br>{len(findings)}</div>
      <div class="metric"><strong>Validations</strong><br>{len(tests)}</div>
    </div>
  </header>
  <section><h2>Findings</h2><table><thead><tr><th>Severity</th><th>Category</th>
    <th>Finding</th><th>Location</th></tr></thead><tbody>{finding_rows}</tbody></table></section>
  <section><h2>Validation</h2><table><thead><tr><th>Command</th><th>Status</th>
    <th>Duration (ms)</th></tr></thead><tbody>{test_rows}</tbody></table></section>
  <section><h2>Policy decisions</h2><table><thead><tr><th>Rule</th><th>Outcome</th>
    <th>Explanation</th></tr></thead><tbody>{policy_rows}</tbody></table></section>
</body>
</html>
"""
