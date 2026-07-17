"""Built-in secret, Python danger, and deployment configuration scanners."""

from __future__ import annotations

import ast
import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from proofstack_core import Finding, FindingCategory, Severity


@dataclass(slots=True)
class SecurityScanResult:
    findings: list[Finding] = field(default_factory=list)
    scanned_files: int = 0
    unavailable_tools: list[str] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class _SecretRule:
    rule_id: str
    title: str
    pattern: re.Pattern[str]
    severity: Severity


_SECRET_RULES = (
    _SecretRule(
        "secret.aws-access-key",
        "AWS access key detected",
        re.compile(r"(?P<secret>AKIA[0-9A-Z]{16})"),
        Severity.CRITICAL,
    ),
    _SecretRule(
        "secret.github-token",
        "GitHub token detected",
        re.compile(r"(?P<secret>gh[pousr]_[A-Za-z0-9]{30,255})"),
        Severity.CRITICAL,
    ),
    _SecretRule(
        "secret.jwt",
        "JWT detected",
        re.compile(r"(?P<secret>eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})"),
        Severity.HIGH,
    ),
    _SecretRule(
        "secret.private-key",
        "Private key detected",
        re.compile(r"(?P<secret>-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"),
        Severity.CRITICAL,
    ),
    _SecretRule(
        "secret.bearer-token",
        "Bearer token detected",
        re.compile(r"(?i)Bearer\s+(?P<secret>[A-Za-z0-9._~+/-]{20,}={0,2})"),
        Severity.CRITICAL,
    ),
    _SecretRule(
        "secret.database-url",
        "Credential-bearing database URL detected",
        re.compile(
            r"(?P<secret>(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s:@/]+:[^\s@/]+@[^\s'\"]+)"
        ),
        Severity.CRITICAL,
    ),
    _SecretRule(
        "secret.assigned-credential",
        "Hard-coded credential detected",
        re.compile(
            r"(?i)(?:api[_-]?key|secret|token|password|passwd|client[_-]?secret)\s*[:=]\s*['\"](?P<secret>[^'\"\s]{8,})['\"]"
        ),
        Severity.HIGH,
    ),
    _SecretRule(
        "secret.dotenv-value",
        "Sensitive .env value detected",
        re.compile(
            r"(?im)^(?:[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY)[A-Z0-9_]*)\s*=\s*['\"]?(?P<secret>[^\s#'\"]{12,})"
        ),
        Severity.HIGH,
    ),
)

_PLACEHOLDER_WORDS = {
    "example",
    "sample",
    "placeholder",
    "changeme",
    "replace_me",
    "replace-me",
    "your_token",
    "your-token",
    "dummy",
    "fake",
    "not-a-real",
    "test-token",
}


class SecretScanner:
    def __init__(self, *, entropy_threshold: float = 4.25, entropy_min_length: int = 28) -> None:
        self.entropy_threshold = entropy_threshold
        self.entropy_min_length = entropy_min_length

    def scan(self, source: str, path: str) -> list[Finding]:
        findings: list[Finding] = []
        seen: set[tuple[int, int]] = set()
        for rule in _SECRET_RULES:
            for match in rule.pattern.finditer(source):
                secret = match.group("secret")
                span = match.span("secret")
                if span in seen or _is_placeholder(secret):
                    continue
                seen.add(span)
                findings.append(self._finding(rule, secret, source, path, span[0]))
        string_pattern = re.compile(
            rf"(?<![A-Za-z0-9])[A-Za-z0-9+/=_-]{{{self.entropy_min_length},}}"
            r"(?![A-Za-z0-9])"
        )
        for match in string_pattern.finditer(source):
            value = match.group(0)
            if (
                match.span() in seen
                or _is_placeholder(value)
                or _entropy(value) < self.entropy_threshold
            ):
                continue
            if value.startswith(("sha256-", "symbol:", "https")):
                continue
            rule = _SecretRule(
                "secret.high-entropy",
                "High-entropy string detected",
                string_pattern,
                Severity.MEDIUM,
            )
            seen.add(match.span())
            findings.append(self._finding(rule, value, source, path, match.start()))
        return findings

    @staticmethod
    def _finding(rule: _SecretRule, secret: str, source: str, path: str, offset: int) -> Finding:
        line = source.count("\n", 0, offset) + 1
        secret_digest = hashlib.sha256(secret.encode()).hexdigest()
        fingerprint = hashlib.sha256(
            f"{rule.rule_id}:{path}:{line}:{secret_digest}".encode()
        ).hexdigest()
        masked = _mask(secret)
        return Finding(
            category=FindingCategory.SECURITY,
            severity=rule.severity,
            title=rule.title,
            description=(
                f"A value matching {rule.rule_id.removeprefix('secret.')} appears at "
                f"{path}:{line}: {masked}."
            ),
            rule_id=rule.rule_id,
            remediation=(
                "Revoke the credential, remove it from history, and load a replacement "
                "from a secret manager."
            ),
            fingerprint=fingerprint,
            file_path=path,
            start_line=line,
            end_line=line,
            evidence={"masked_value": masked, "secret_sha256": secret_digest},
        )


@dataclass(slots=True, frozen=True)
class _Danger:
    rule_id: str
    severity: Severity
    title: str
    remediation: str


_DANGERS = {
    "eval": _Danger(
        "python.eval",
        Severity.HIGH,
        "Dynamic eval call",
        "Replace eval with an explicit parser or dispatch table.",
    ),
    "exec": _Danger(
        "python.exec",
        Severity.HIGH,
        "Dynamic exec call",
        "Remove dynamic code execution and use a constrained interface.",
    ),
    "pickle.loads": _Danger(
        "python.pickle-loads",
        Severity.HIGH,
        "Unsafe pickle deserialization",
        "Use a non-executable data format and validate its schema.",
    ),
    "os.system": _Danger(
        "python.os-system",
        Severity.HIGH,
        "Shell command execution",
        "Use subprocess with an argument array and a fixed executable allowlist.",
    ),
    "tempfile.mktemp": _Danger(
        "python.insecure-tempfile",
        Severity.HIGH,
        "Insecure temporary filename",
        "Use NamedTemporaryFile or TemporaryDirectory with safe creation semantics.",
    ),
    "hashlib.md5": _Danger(
        "python.weak-hash",
        Severity.MEDIUM,
        "Weak MD5 hash",
        "Use SHA-256 or a purpose-built password hashing algorithm.",
    ),
    "hashlib.sha1": _Danger(
        "python.weak-hash",
        Severity.MEDIUM,
        "Weak SHA-1 hash",
        "Use SHA-256 or stronger where collision resistance matters.",
    ),
}


class DangerousPatternScanner:
    def scan(self, source: str, path: str) -> list[Finding]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _name(node.func)
            danger = _DANGERS.get(name)
            if danger is not None:
                findings.append(_danger_finding(danger, path, node.lineno))
            if name in {
                "subprocess.run",
                "subprocess.call",
                "subprocess.Popen",
                "subprocess.check_call",
                "subprocess.check_output",
            } and _keyword_true(node, "shell"):
                findings.append(
                    _danger_finding(
                        _Danger(
                            "python.subprocess-shell",
                            Severity.CRITICAL,
                            "Subprocess uses shell=True",
                            "Pass a fixed argument array with shell=False.",
                        ),
                        path,
                        node.lineno,
                    )
                )
            if name in {"yaml.load", "yaml.unsafe_load"} and not _safe_yaml_loader(node):
                findings.append(
                    _danger_finding(
                        _Danger(
                            "python.unsafe-yaml-load",
                            Severity.HIGH,
                            "Unsafe YAML deserialization",
                            "Use yaml.safe_load or SafeLoader.",
                        ),
                        path,
                        node.lineno,
                    )
                )
            if _keyword_false(node, "verify"):
                findings.append(
                    _danger_finding(
                        _Danger(
                            "python.tls-verification-disabled",
                            Severity.HIGH,
                            "TLS certificate verification disabled",
                            "Enable certificate verification and configure a trusted CA bundle.",
                        ),
                        path,
                        node.lineno,
                    )
                )
            if name.endswith("jwt.decode") or name == "jwt.decode":
                algorithms = next(
                    (item.value for item in node.keywords if item.arg == "algorithms"), None
                )
                options = next(
                    (item.value for item in node.keywords if item.arg == "options"), None
                )
                if algorithms is None or _contains_verify_false(options):
                    findings.append(
                        _danger_finding(
                            _Danger(
                                "python.jwt-validation-incomplete",
                                Severity.HIGH,
                                "JWT validation may be incomplete",
                                (
                                    "Require an explicit algorithm allowlist and signature "
                                    "verification."
                                ),
                            ),
                            path,
                            node.lineno,
                        )
                    )
            if _looks_like_sql_concatenation(node):
                findings.append(
                    _danger_finding(
                        _Danger(
                            "python.sql-string-concatenation",
                            Severity.HIGH,
                            "SQL statement is dynamically constructed",
                            "Use bound parameters through the database driver or ORM.",
                        ),
                        path,
                        node.lineno,
                    )
                )
        origin_match = re.search(r"allow_origins\s*=\s*\[\s*['\"]\*['\"]\s*\]", source)
        credentials_match = re.search(r"allow_credentials\s*=\s*True", source)
        if origin_match and credentials_match:
            line = source[: origin_match.start()].count("\n") + 1
            findings.append(
                _danger_finding(
                    _Danger(
                        "python.cors-wildcard-credentials",
                        Severity.CRITICAL,
                        "Wildcard CORS is combined with credentials",
                        "Configure an explicit trusted origin allowlist.",
                    ),
                    path,
                    line,
                )
            )
        if re.search(r"\bdebug\s*=\s*True\b", source):
            match = re.search(r"\bdebug\s*=\s*True\b", source)
            line = source[: match.start()].count("\n") + 1 if match else 1
            findings.append(
                _danger_finding(
                    _Danger(
                        "python.debug-enabled",
                        Severity.MEDIUM,
                        "Debug mode is enabled",
                        "Disable debug mode outside an explicitly isolated development profile.",
                    ),
                    path,
                    line,
                )
            )
        traversal_match = re.search(
            r"\b(?:open|Path)\s*\(\s*(?:request\.|user_|filename\b|path_param\b)", source
        )
        if traversal_match:
            line = source[: traversal_match.start()].count("\n") + 1
            findings.append(
                _danger_finding(
                    _Danger(
                        "python.path-traversal-input",
                        Severity.HIGH,
                        "User-controlled path reaches a filesystem operation",
                        (
                            "Resolve against a fixed root and reject absolute paths and "
                            "parent traversal."
                        ),
                    ),
                    path,
                    line,
                )
            )
        return _unique_findings(findings)


class FileSecurityScanner:
    def scan(
        self, files: Mapping[str, str], *, modes: Mapping[str, int] | None = None
    ) -> list[Finding]:
        findings: list[Finding] = []
        modes = modes or {}
        for path, source in files.items():
            lowered = path.lower()
            name = PurePosixPath(path).name.lower()
            if name == ".env" or (
                name.startswith(".env.") and name not in {".env.example", ".env.sample"}
            ):
                findings.append(
                    _config_finding(
                        "file.committed-env",
                        Severity.HIGH,
                        "Sensitive environment file is present",
                        path,
                        1,
                        (
                            "Remove the environment file from version control and rotate "
                            "exposed values."
                        ),
                    )
                )
            mode = modes.get(path)
            if mode is not None and mode & 0o002:
                findings.append(
                    _config_finding(
                        "file.world-writable",
                        Severity.HIGH,
                        "File is world-writable",
                        path,
                        1,
                        "Remove world-write permission.",
                    )
                )
            if name == "dockerfile" or name.endswith(".dockerfile"):
                findings.extend(_scan_dockerfile(source, path))
            if ".github/workflows/" in lowered and lowered.endswith((".yml", ".yaml")):
                findings.extend(_scan_workflow(source, path))
            if name in {"compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml"}:
                findings.extend(_scan_compose(source, path))
        return _unique_findings(findings)


class SecurityAnalyzer:
    def __init__(self) -> None:
        self.secrets = SecretScanner()
        self.dangerous = DangerousPatternScanner()
        self.files = FileSecurityScanner()

    def scan(
        self,
        files: Mapping[str, str],
        *,
        modes: Mapping[str, int] | None = None,
    ) -> SecurityScanResult:
        findings: list[Finding] = []
        for path, source in files.items():
            findings.extend(self.secrets.scan(source, path))
            if path.endswith(".py"):
                findings.extend(self.dangerous.scan(source, path))
        findings.extend(self.files.scan(files, modes=modes))
        return SecurityScanResult(_unique_findings(findings), len(files))


def _scan_dockerfile(source: str, path: str) -> list[Finding]:
    findings: list[Finding] = []
    for match in re.finditer(r"^\s*FROM\s+([^\s]+)", source, re.I | re.M):
        image = match.group(1)
        if ":" not in image or image.endswith(":latest"):
            line = source.count("\n", 0, match.start()) + 1
            findings.append(
                _config_finding(
                    "docker.floating-base-image",
                    Severity.MEDIUM,
                    "Docker base image is not pinned",
                    path,
                    line,
                    "Pin the image to a version or immutable digest.",
                )
            )
    user_matches = list(re.finditer(r"^\s*USER\s+([^\s]+)", source, re.I | re.M))
    if not user_matches or user_matches[-1].group(1).lower() in {"root", "0", "0:0"}:
        findings.append(
            _config_finding(
                "docker.root-user",
                Severity.HIGH,
                "Container runs as root",
                path,
                1,
                "Create and select a dedicated non-root runtime user.",
            )
        )
    for match in re.finditer(r"\bchmod\s+(?:-R\s+)?777\b", source, re.I):
        findings.append(
            _config_finding(
                "docker.world-writable",
                Severity.HIGH,
                "Docker build creates world-writable files",
                path,
                source.count("\n", 0, match.start()) + 1,
                "Use the narrowest required file permissions.",
            )
        )
    return findings


def _scan_workflow(source: str, path: str) -> list[Finding]:
    findings: list[Finding] = []
    for match in re.finditer(r"^\s*-?\s*uses:\s*([^\s#]+)", source, re.M):
        action = match.group(1)
        if action.startswith(("./", "docker://")):
            continue
        reference = action.rsplit("@", 1)[-1] if "@" in action else ""
        if not re.fullmatch(r"[0-9a-fA-F]{40}", reference):
            findings.append(
                _config_finding(
                    "github-action.unpinned",
                    Severity.MEDIUM,
                    "GitHub Action is not pinned to a commit",
                    path,
                    source.count("\n", 0, match.start()) + 1,
                    "Pin the action to a reviewed full commit SHA.",
                )
            )
    return findings


def _scan_compose(source: str, path: str) -> list[Finding]:
    findings: list[Finding] = []
    for match in re.finditer(
        (
            r"(?im)^\s*[A-Z0-9_]*(?:PASSWORD|TOKEN|SECRET|API_KEY)[A-Z0-9_]*"
            r"\s*:\s*['\"]?([^\s'\"$][^\s'\"]*)"
        ),
        source,
    ):
        findings.append(
            _config_finding(
                "compose.literal-secret",
                Severity.CRITICAL,
                "Compose file contains a literal secret",
                path,
                source.count("\n", 0, match.start()) + 1,
                "Use a runtime secret source or environment variable reference.",
            )
        )
    debug_port_match = re.search(r"(?:0\.0\.0\.0:)?(?:5678|9229|2345):", source)
    if debug_port_match:
        findings.append(
            _config_finding(
                "compose.debug-port",
                Severity.MEDIUM,
                "Compose exposes a common debug port",
                path,
                source.count("\n", 0, debug_port_match.start()) + 1,
                "Remove the debug port from non-development profiles.",
            )
        )
    wildcard_bind_match = re.search(r"(?:--host\s+|host\s*:\s*['\"]?)0\.0\.0\.0\b", source, re.I)
    if wildcard_bind_match:
        findings.append(
            _config_finding(
                "network.wildcard-bind",
                Severity.MEDIUM,
                "Service binds to every network interface",
                path,
                source.count("\n", 0, wildcard_bind_match.start()) + 1,
                "Bind to a private interface or document the required network boundary.",
            )
        )
    return findings


def _danger_finding(danger: _Danger, path: str, line: int) -> Finding:
    fingerprint = hashlib.sha256(f"{danger.rule_id}:{path}:{line}".encode()).hexdigest()
    return Finding(
        category=FindingCategory.SECURITY,
        severity=danger.severity,
        title=danger.title,
        description=f"{danger.title} appears at {path}:{line}.",
        rule_id=danger.rule_id,
        remediation=danger.remediation,
        fingerprint=fingerprint,
        file_path=path,
        start_line=line,
        end_line=line,
    )


def _config_finding(
    rule_id: str, severity: Severity, title: str, path: str, line: int, remediation: str
) -> Finding:
    return Finding(
        category=FindingCategory.SECURITY,
        severity=severity,
        title=title,
        description=f"{title} at {path}:{line}.",
        rule_id=rule_id,
        remediation=remediation,
        fingerprint=hashlib.sha256(f"{rule_id}:{path}:{line}".encode()).hexdigest(),
        file_path=path,
        start_line=line,
        end_line=line,
    )


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _name(node.value)
        return f"{owner}.{node.attr}" if owner else node.attr
    return ""


def _keyword_true(node: ast.Call, name: str) -> bool:
    return any(
        item.arg == name and isinstance(item.value, ast.Constant) and item.value.value is True
        for item in node.keywords
    )


def _keyword_false(node: ast.Call, name: str) -> bool:
    return any(
        item.arg == name and isinstance(item.value, ast.Constant) and item.value.value is False
        for item in node.keywords
    )


def _safe_yaml_loader(node: ast.Call) -> bool:
    return any(
        item.arg == "Loader" and _name(item.value).endswith(("SafeLoader", "CSafeLoader"))
        for item in node.keywords
    )


def _contains_verify_false(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Dict):
        return False
    for key, value in zip(node.keys, node.values, strict=True):
        if (
            isinstance(key, ast.Constant)
            and key.value == "verify_signature"
            and isinstance(value, ast.Constant)
            and value.value is False
        ):
            return True
    return False


def _looks_like_sql_concatenation(node: ast.Call) -> bool:
    name = _name(node.func).lower()
    if not name.endswith(("execute", "executemany")) or not node.args:
        return False
    value = node.args[0]
    rendered = ast.unparse(value).lower()
    sql = any(keyword in rendered for keyword in ("select ", "insert ", "update ", "delete "))
    dynamic = isinstance(value, ast.BinOp | ast.JoinedStr) or ".format(" in rendered
    return sql and dynamic


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    if any(word in lowered for word in _PLACEHOLDER_WORDS):
        return True
    compact = re.sub(r"[^a-z0-9]", "", lowered)
    return len(set(compact)) <= 3 or re.fullmatch(r"(?:abc|123|xyz)+", compact) is not None


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * min(12, len(value) - 7)}{value[-3:]}"


def _entropy(value: str) -> float:
    counts = Counter(value)
    return -sum((count / len(value)) * math.log2(count / len(value)) for count in counts.values())


def _unique_findings(findings: Iterable[Finding]) -> list[Finding]:
    return list({item.fingerprint: item for item in findings}.values())
