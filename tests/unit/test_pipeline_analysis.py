from __future__ import annotations

from pathlib import Path

from proofstack_analyzers import default_analysis_stages
from proofstack_core import AnalysisContext, AnalysisPipeline, Finding, FunctionalStage, StageStatus


def test_analysis_pipeline_runs_real_deterministic_stages(tmp_path: Path) -> None:
    app = tmp_path / "app.py"
    app.write_text(
        "import subprocess\n"
        "def calculate(value):\n"
        "    subprocess.run(['echo', str(value)], shell=True)\n"
        "    return value\n",
        encoding="utf-8",
    )
    (tmp_path / "test_app.py").write_text(
        "from app import calculate\ndef test_calculate():\n    assert calculate(1) == 1\n",
        encoding="utf-8",
    )
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,4 @@
+import subprocess
 def calculate(value):
+    subprocess.run(['echo', str(value)], shell=True)
     return value
"""
    context = AnalysisContext(
        "analysis-1",
        tmp_path,
        diff_text=diff,
        requirement_text="# Calculate values\nThe calculate function must return a value.\n",
    )
    result = AnalysisPipeline(default_analysis_stages()).run(context)

    assert result.status is StageStatus.COMPLETED
    assert result.progress == 100
    assert context.data["changed_symbols"] == ["app.calculate"]
    assert context.data["graph_data"]["nodes"]
    assert context.data["requirement_mapping"].coverage_score == 1.0
    assert "python.subprocess-shell" in {item.rule_id for item in result.findings}


def test_pipeline_contains_stage_failures_and_returns_user_message(tmp_path: Path) -> None:
    def explode(context: AnalysisContext) -> tuple[dict[str, object], list[Finding]]:
        raise RuntimeError(f"cannot analyze {context.analysis_id}")

    context = AnalysisContext("broken-analysis", tmp_path)
    pipeline = AnalysisPipeline([FunctionalStage("EXPLODE", explode)])
    result = pipeline.run(context)

    assert result.status is StageStatus.FAILED
    assert result.stages[0].error_code == "stage_execution_failed"
    assert (
        result.error_summary
        == "The EXPLODE stage could not be completed: cannot analyze broken-analysis"
    )


def test_pipeline_cancellation_stops_before_next_stage(tmp_path: Path) -> None:
    context = AnalysisContext("cancelled", tmp_path)
    context.cancel()
    pipeline = AnalysisPipeline([FunctionalStage("NOOP", lambda _: ({}, []))])

    result = pipeline.run(context)

    assert result.status is StageStatus.CANCELLED
    assert result.stages == []
