from __future__ import annotations

import json

import pytest
from proofstack_analyzers import (
    ConfigurationAnalyzer,
    DatabaseImpactAnalyzer,
    DependencyAnalyzer,
    DeterministicRequirementMapper,
    EvidenceCandidate,
    OpenAICompatibleConfig,
    OpenAICompatibleRequirementMapper,
    RequirementSpec,
    TestGapAnalyzer,
)


def test_configuration_analyzer_detects_undocumented_required_environment() -> None:
    current = {
        "app/config.py": (
            'import os\nTOKEN = os.environ["PAYMENTS_TOKEN"]\nPORT = os.getenv("PORT", "8000")\n'
        ),
        ".env.example": "PORT=8000\n",
    }
    result = ConfigurationAnalyzer().analyze(
        current, previous_files={".env.example": "PORT=8000\n"}
    )

    assert result.undocumented_variables == ["PAYMENTS_TOKEN"]
    finding = result.findings[0]
    assert finding.rule_id == "config.undocumented-environment-variable"
    assert finding.severity.value == "high"


def test_configuration_analyzer_parses_yaml_and_detects_compose_drift() -> None:
    current = {
        "app/config.py": 'import os\nTOKEN = os.environ["PAYMENTS_TOKEN"]\n',
        "settings.yml": "service:\n  timeout: 10\n",
        "compose.yml": "services:\n  api:\n    environment:\n      PORT: 8000\n",
    }
    previous = {"settings.yml": "service:\n  timeout: 10\n  retries: 3\n"}
    result = ConfigurationAnalyzer().analyze(current, previous_files=previous)

    assert "settings.yml:service:retries" in result.removed_keys
    assert result.compose_drift == ["PAYMENTS_TOKEN"]
    assert "config.compose-environment-drift" in {item.rule_id for item in result.findings}


def test_dependency_analyzer_reports_changes_urls_and_missing_lockfile() -> None:
    current = {
        "requirements.txt": "httpx>=0.27\nplugin @ git+https://example.invalid/plugin.git@main\n",
        "package.json": '{"dependencies":{"react":"^19.0.0"}}',
    }
    previous = {"requirements.txt": "httpx==0.26.0\n"}
    result = DependencyAnalyzer().analyze(current, previous_files=previous)

    change = next(item for item in result.changes if item.name == "httpx")
    assert change.change_type == "upgraded"
    rules = {item.rule_id for item in result.findings}
    assert "dependency.direct-url" in rules
    assert "dependency.javascript-lockfile-missing" in rules
    assert "dependency.unpinned" in rules

    python_result = DependencyAnalyzer().analyze(
        {"pyproject.toml": '[project]\ndependencies = ["httpx==0.28.0"]\n'}
    )
    assert "dependency.python-lockfile-missing" in {item.rule_id for item in python_result.findings}


def test_database_analyzer_flags_destructive_and_missing_migration_changes() -> None:
    destructive = {
        "alembic/versions/002_drop.py": (
            "def upgrade():\n    op.drop_column('users', 'name')\ndef downgrade():\n    pass\n"
        )
    }
    result = DatabaseImpactAnalyzer().analyze(destructive)
    rules = {item.rule_id for item in result.findings}

    assert "database.drop-column" in rules
    assert "database.irreversible-migration" in rules

    model_result = DatabaseImpactAnalyzer().analyze(
        {"app/models.py": "class User:\n    email = mapped_column(String)\n"},
        previous_files={"app/models.py": "class User:\n    pass\n"},
    )
    assert "database.model-change-without-migration" in {
        item.rule_id for item in model_result.findings
    }

    existing_migration_result = DatabaseImpactAnalyzer().analyze(
        {
            "app/models.py": "class User:\n    email = mapped_column(String)\n",
            "alembic/versions/001_existing.py": "def upgrade():\n    return None\n",
        },
        previous_files={
            "app/models.py": "class User:\n    pass\n",
            "alembic/versions/001_existing.py": "def upgrade():\n    return None\n",
        },
    )
    assert "database.model-change-without-migration" in {
        item.rule_id for item in existing_migration_result.findings
    }


def test_deterministic_requirement_mapping_links_files_symbols_tests_and_routes() -> None:
    requirements = [
        RequirementSpec(
            "REQ-1",
            "Create invoice endpoint",
            "POST /invoices must persist an invoice",
            ("A test proves invoice creation",),
        ),
        RequirementSpec("REQ-2", "Export a PDF receipt", "Users can download PDF receipts"),
    ]
    candidates = [
        EvidenceCandidate("file:app/invoices.py", "file", "invoice creation", "app/invoices.py"),
        EvidenceCandidate(
            "symbol:create_invoice",
            "symbol",
            "create invoice handler",
            symbol="app.invoices.create_invoice",
        ),
        EvidenceCandidate(
            "test:tests/test_invoices.py",
            "test",
            "test create invoice",
            "tests/test_invoices.py",
        ),
        EvidenceCandidate("route:post-invoices", "route", "POST /invoices create invoice"),
    ]
    result = DeterministicRequirementMapper(support_threshold=0.2).map_requirements(
        requirements, candidates
    )

    assert result.mappings[0].supported
    assert result.mappings[0].changed_files == ["app/invoices.py"]
    assert result.mappings[0].tests == ["tests/test_invoices.py"]
    assert "REQ-2" in result.unsupported_requirement_ids
    assert result.coverage_score == 0.5


def test_openai_compatible_mapper_is_opt_in_and_validates_evidence_ids() -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            content = {
                "mappings": [
                    {
                        "requirement_id": "REQ-1",
                        "candidate_ids": ["file:service.py", "unknown"],
                        "score": 0.9,
                        "explanation": "The file implements the requested service.",
                    }
                ]
            }
            return {"choices": [{"message": {"content": json.dumps(content)}}]}

    class Client:
        def post(self, url: str, **kwargs: object) -> Response:
            assert url == "https://llm.invalid/v1/chat/completions"
            assert "json" in kwargs
            return Response()

    requirements = [RequirementSpec("REQ-1", "Update service")]
    candidates = [EvidenceCandidate("file:service.py", "file", "updated service", "service.py")]
    disabled = OpenAICompatibleRequirementMapper(OpenAICompatibleConfig())
    with pytest.raises(RuntimeError, match="disabled"):
        disabled.map_requirements(requirements, candidates)

    config = OpenAICompatibleConfig(
        enabled=True,
        base_url="https://llm.invalid/v1",
        api_key="sensitive-value",
        model="local-model",
    )
    result = OpenAICompatibleRequirementMapper(config, client=Client()).map_requirements(
        requirements, candidates
    )
    assert result.provider == "openai_compatible"
    assert result.mappings[0].changed_files == ["service.py"]
    assert "sensitive-value" not in repr(config)


def test_test_gap_analysis_maps_imports_and_suggests_missing_cases() -> None:
    files = {
        "app/calculator.py": "def total(values):\n    return sum(values)\n",
        "app/payment.py": "def charge(value):\n    return value\n",
        "tests/test_calculator.py": (
            "from app.calculator import total\n"
            "def test_total(sample_values):\n    assert total(sample_values)\n"
        ),
    }
    result = TestGapAnalyzer().analyze(
        files,
        ["app/calculator.py", "app/payment.py"],
        changed_symbols=["app.calculator.total", "app.payment.charge"],
        high_risk_sources=["app/payment.py"],
    )

    assert result.source_to_tests["app/calculator.py"] == ["tests/test_calculator.py"]
    assert result.uncovered_sources == ["app/payment.py"]
    assert result.suggestions[0].recommended_path == "tests/test_payment.py"
    assert 0 < result.evidence_score < 1
