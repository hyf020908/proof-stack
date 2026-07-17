"""Offline-first requirement-to-evidence mapping with an optional HTTP adapter."""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True, frozen=True)
class RequirementSpec:
    id: str
    title: str
    description: str = ""
    acceptance_criteria: tuple[str, ...] = ()
    source: str = "user"

    @property
    def text(self) -> str:
        return " ".join((self.title, self.description, *self.acceptance_criteria)).strip()


@dataclass(slots=True, frozen=True)
class EvidenceCandidate:
    id: str
    kind: str
    text: str
    path: str | None = None
    symbol: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class EvidenceMatch:
    candidate_id: str
    kind: str
    score: float
    explanation: str


@dataclass(slots=True)
class RequirementMapping:
    requirement_id: str
    title: str
    score: float
    supported: bool
    changed_files: list[str] = field(default_factory=list)
    changed_symbols: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    evidence: list[EvidenceMatch] = field(default_factory=list)


@dataclass(slots=True)
class RequirementMappingResult:
    mappings: list[RequirementMapping]
    coverage_score: float
    unsupported_requirement_ids: list[str]
    unmentioned_changed_files: list[str]
    provider: str = "deterministic"


@runtime_checkable
class RequirementMapperProvider(Protocol):
    def map_requirements(
        self,
        requirements: Sequence[RequirementSpec],
        candidates: Sequence[EvidenceCandidate],
    ) -> RequirementMappingResult:
        """Map requirement statements to verifiable local evidence."""


class DeterministicRequirementMapper:
    def __init__(self, *, support_threshold: float = 0.2, match_limit: int = 8) -> None:
        if not 0 <= support_threshold <= 1:
            raise ValueError("support_threshold must be between zero and one")
        self.support_threshold = support_threshold
        self.match_limit = match_limit

    def map_requirements(
        self,
        requirements: Sequence[RequirementSpec],
        candidates: Sequence[EvidenceCandidate],
    ) -> RequirementMappingResult:
        corpus = [_tokens(item.text) for item in requirements] + [
            _tokens(item.text) for item in candidates
        ]
        inverse_document_frequency = _idf(corpus)
        candidate_vectors = {
            candidate.id: _tfidf(_tokens(_candidate_text(candidate)), inverse_document_frequency)
            for candidate in candidates
        }
        mappings: list[RequirementMapping] = []
        mentioned_files: set[str] = set()
        for requirement in requirements:
            requirement_tokens = _tokens(requirement.text)
            requirement_vector = _tfidf(requirement_tokens, inverse_document_frequency)
            scored: list[tuple[float, EvidenceCandidate, str]] = []
            for candidate in candidates:
                similarity = _cosine(requirement_vector, candidate_vectors[candidate.id])
                overlap = _keyword_overlap(requirement_tokens, _tokens(_candidate_text(candidate)))
                explicit = _explicit_reference(requirement.text, candidate)
                kind_bonus = 0.04 if candidate.kind in {"test", "route"} and overlap > 0 else 0.0
                score = min(1.0, similarity * 0.62 + overlap * 0.28 + explicit * 0.3 + kind_bonus)
                if score > 0:
                    reasons = []
                    if explicit:
                        reasons.append("explicit name or path reference")
                    if overlap:
                        reasons.append("shared domain terms")
                    if similarity:
                        reasons.append("local TF-IDF similarity")
                    scored.append((score, candidate, ", ".join(reasons)))
            scored.sort(key=lambda item: (-item[0], item[1].id))
            matches = [
                EvidenceMatch(candidate.id, candidate.kind, round(score, 4), explanation)
                for score, candidate, explanation in scored[: self.match_limit]
                if score >= self.support_threshold * 0.6
            ]
            best_score = scored[0][0] if scored else 0.0
            supported = best_score >= self.support_threshold
            mapping = RequirementMapping(
                requirement_id=requirement.id,
                title=requirement.title,
                score=round(best_score, 4),
                supported=supported,
                evidence=matches,
            )
            for match in matches:
                candidate = next(item for item in candidates if item.id == match.candidate_id)
                if candidate.path and candidate.kind in {"file", "diff"}:
                    mapping.changed_files.append(candidate.path)
                    mentioned_files.add(candidate.path)
                if candidate.symbol or candidate.kind == "symbol":
                    mapping.changed_symbols.append(candidate.symbol or candidate.id)
                if candidate.kind == "test":
                    mapping.tests.append(candidate.path or candidate.id)
                if candidate.kind == "route":
                    mapping.routes.append(candidate.id)
            mapping.changed_files = sorted(set(mapping.changed_files))
            mapping.changed_symbols = sorted(set(mapping.changed_symbols))
            mapping.tests = sorted(set(mapping.tests))
            mapping.routes = sorted(set(mapping.routes))
            mappings.append(mapping)
        unsupported = [item.requirement_id for item in mappings if not item.supported]
        coverage = sum(item.supported for item in mappings) / len(mappings) if mappings else 1.0
        all_changed_files = {
            item.path for item in candidates if item.kind in {"file", "diff"} and item.path
        }
        return RequirementMappingResult(
            mappings=mappings,
            coverage_score=round(coverage, 4),
            unsupported_requirement_ids=unsupported,
            unmentioned_changed_files=sorted(all_changed_files - mentioned_files),
        )


class MockRequirementMapper:
    def __init__(self, result: RequirementMappingResult | None = None) -> None:
        self.result = result

    def map_requirements(
        self,
        requirements: Sequence[RequirementSpec],
        candidates: Sequence[EvidenceCandidate],
    ) -> RequirementMappingResult:
        if self.result is not None:
            return self.result
        mappings = [RequirementMapping(item.id, item.title, 1.0, True) for item in requirements]
        return RequirementMappingResult(mappings, 1.0, [], [], provider="mock")


@dataclass(slots=True)
class OpenAICompatibleConfig:
    enabled: bool = False
    base_url: str = "https://api.openai.com/v1"
    api_key: str = field(default="", repr=False)
    model: str = ""
    timeout_seconds: float = 20.0
    max_retries: int = 2

    @classmethod
    def from_environment(cls) -> OpenAICompatibleConfig:
        return cls(
            enabled=os.getenv("PROOFSTACK_LLM_ENABLED", "false").lower() in {"1", "true", "yes"},
            base_url=os.getenv("PROOFSTACK_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            api_key=os.getenv("PROOFSTACK_LLM_API_KEY", ""),
            model=os.getenv("PROOFSTACK_LLM_MODEL", ""),
        )


class OpenAICompatibleRequirementMapper:
    def __init__(self, config: OpenAICompatibleConfig, *, client: Any | None = None) -> None:
        self.config = config
        self._client = client

    def map_requirements(
        self,
        requirements: Sequence[RequirementSpec],
        candidates: Sequence[EvidenceCandidate],
    ) -> RequirementMappingResult:
        if not self.config.enabled:
            raise RuntimeError("LLM requirement mapping is disabled")
        if not self.config.api_key or not self.config.model:
            raise RuntimeError("LLM mapping requires an API key and model")
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for the optional LLM adapter") from exc
        client = self._client or httpx.Client(timeout=self.config.timeout_seconds)
        payload = {
            "model": self.config.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Map requirements only to supplied evidence. Return JSON with a "
                        "mappings array. Each item must contain requirement_id, candidate_ids, "
                        "score, and explanation."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "requirements": [
                                {"id": item.id, "title": item.title, "text": item.text}
                                for item in requirements
                            ],
                            "evidence": [
                                {"id": item.id, "kind": item.kind, "text": item.text}
                                for item in candidates
                            ],
                        },
                        ensure_ascii=True,
                    ),
                },
            ],
        }
        response = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = client.post(
                    f"{self.config.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                break
            except Exception:
                if attempt >= self.config.max_retries:
                    raise RuntimeError(
                        "The configured LLM mapping endpoint did not respond successfully"
                    ) from None
        if response is None:
            raise RuntimeError("The configured LLM mapping endpoint returned no response")
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
            mapped = json.loads(content) if isinstance(content, str) else content
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("The LLM mapping endpoint returned an invalid response") from exc
        return _mapping_result_from_json(mapped, requirements, candidates)


def build_evidence_candidates(
    *,
    changed_files: Sequence[str] = (),
    changed_symbols: Sequence[str] = (),
    tests: Sequence[str] = (),
    routes: Sequence[str] = (),
    file_contents: Mapping[str, str] | None = None,
) -> list[EvidenceCandidate]:
    file_contents = file_contents or {}
    result = [
        EvidenceCandidate(
            f"file:{path}",
            "file",
            f"{path} {file_contents.get(path, '')[:20_000]}",
            path=path,
        )
        for path in changed_files
    ]
    result.extend(
        EvidenceCandidate(f"symbol:{symbol}", "symbol", symbol, symbol=symbol)
        for symbol in changed_symbols
    )
    result.extend(EvidenceCandidate(f"test:{path}", "test", path, path=path) for path in tests)
    result.extend(EvidenceCandidate(f"route:{route}", "route", route) for route in routes)
    return result


def _mapping_result_from_json(
    data: Any,
    requirements: Sequence[RequirementSpec],
    candidates: Sequence[EvidenceCandidate],
) -> RequirementMappingResult:
    if not isinstance(data, dict) or not isinstance(data.get("mappings"), list):
        raise RuntimeError("The LLM mapping response does not contain mappings")
    candidate_map = {item.id: item for item in candidates}
    requirement_map = {item.id: item for item in requirements}
    mappings: list[RequirementMapping] = []
    mentioned: set[str] = set()
    for raw in data["mappings"]:
        if not isinstance(raw, dict) or raw.get("requirement_id") not in requirement_map:
            continue
        requirement = requirement_map[raw["requirement_id"]]
        score = max(0.0, min(1.0, float(raw.get("score", 0))))
        matches = []
        mapping = RequirementMapping(requirement.id, requirement.title, score, score >= 0.5)
        for candidate_id in raw.get("candidate_ids", []):
            candidate = candidate_map.get(candidate_id)
            if candidate is None:
                continue
            matches.append(
                EvidenceMatch(candidate.id, candidate.kind, score, str(raw.get("explanation", "")))
            )
            if candidate.path and candidate.kind in {"file", "diff"}:
                mapping.changed_files.append(candidate.path)
                mentioned.add(candidate.path)
            elif candidate.kind == "test":
                mapping.tests.append(candidate.path or candidate.id)
            elif candidate.kind == "route":
                mapping.routes.append(candidate.id)
            elif candidate.symbol:
                mapping.changed_symbols.append(candidate.symbol)
        mapping.evidence = matches
        mappings.append(mapping)
    seen = {item.requirement_id for item in mappings}
    mappings.extend(
        RequirementMapping(item.id, item.title, 0.0, False)
        for item in requirements
        if item.id not in seen
    )
    unsupported = [item.requirement_id for item in mappings if not item.supported]
    changed = {item.path for item in candidates if item.kind in {"file", "diff"} and item.path}
    return RequirementMappingResult(
        mappings,
        round(sum(item.supported for item in mappings) / len(mappings), 4) if mappings else 1.0,
        unsupported,
        sorted(changed - mentioned),
        provider="openai_compatible",
    )


def _candidate_text(candidate: EvidenceCandidate) -> str:
    return " ".join(filter(None, (candidate.text, candidate.path, candidate.symbol)))


def _tokens(text: str) -> list[str]:
    raw_tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_/-]{1,}|[\u4e00-\u9fff]{2,}", text.lower())
    tokens: list[str] = []
    for token in raw_tokens:
        if re.fullmatch(r"[\u4e00-\u9fff]{3,}", token):
            tokens.extend(token[index : index + 2] for index in range(len(token) - 1))
        else:
            tokens.append(token)
    stop = {"the", "and", "for", "with", "that", "this", "from", "should", "must", "into"}
    return [token for token in tokens if token not in stop]


def _idf(documents: Sequence[Sequence[str]]) -> dict[str, float]:
    total = max(1, len(documents))
    frequency: Counter[str] = Counter()
    for document in documents:
        frequency.update(set(document))
    return {token: math.log((1 + total) / (1 + count)) + 1 for token, count in frequency.items()}


def _tfidf(tokens: Sequence[str], idf: dict[str, float]) -> dict[str, float]:
    counts = Counter(tokens)
    total = max(1, len(tokens))
    return {token: count / total * idf.get(token, 1.0) for token, count in counts.items()}


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    numerator = sum(value * right.get(token, 0.0) for token, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _keyword_overlap(left: Sequence[str], right: Sequence[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    return len(left_set & right_set) / max(1, min(len(left_set), len(right_set)))


def _explicit_reference(text: str, candidate: EvidenceCandidate) -> float:
    lowered = text.lower()
    values = [candidate.path, candidate.symbol, candidate.id]
    for value in values:
        if not value:
            continue
        normalized = value.lower()
        basename = normalized.rsplit("/", 1)[-1]
        short = normalized.rsplit(".", 1)[-1]
        if normalized in lowered or basename in lowered or (len(short) > 3 and short in lowered):
            return 1.0
    return 0.0
