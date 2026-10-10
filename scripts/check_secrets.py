"""Scan repository text for likely hardcoded secrets without displaying values."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import os
from pathlib import Path
import re


EXCLUDED_DIRECTORIES = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".cache", "cache", "dist", "build",
    "coverage", "htmlcov",
}
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
    ".7z", ".gz", ".tar", ".exe", ".dll", ".so", ".dylib", ".pyc",
    ".pyo", ".woff", ".woff2", ".ttf", ".otf", ".mp3", ".wav", ".mp4",
    ".mov", ".sqlite", ".db", ".xlsx", ".docx", ".pptx", ".parquet",
    ".npz", ".npy",
}
CONFIG_SUFFIXES = {
    ".env", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".json",
    ".cmd", ".bat", ".sh", ".bash",
}
KEY_PATTERN = re.compile(r"(?<![\w-])sk-[A-Za-z0-9]{20,}(?![A-Za-z0-9])")
ASSIGNMENT_PATTERN = re.compile(
    r"(?<![\w])(?P<quote>['\"]?)(?P<name>api_key|token|secret)(?P=quote)"
    r"\s*\]?\s*(?:(?::\s*[^=\r\n]{1,80})?=|:)\s*",
    re.IGNORECASE,
)
AUTHORIZATION_PATTERN = re.compile(
    r"(?<![\w])(?P<quote>['\"]?)authorization(?P=quote)"
    r"\s*\]?\s*(?:=|:)\s*",
    re.IGNORECASE,
)
QUOTED_VALUE_PATTERN = re.compile(
    r"^(?P<prefix>br|rb|fr|rf|r|b|u|f)?"
    r"(?P<quote>\"{3}|'{3}|['\"])(?P<value>(?:\\.|(?!(?P=quote)).)*)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
PLACEHOLDERS = {
    "", "...", "sk-...", "api_key", "token", "secret", "api-key",
    "your-api-key", "your_api_key", "your-token", "your_token", "your-secret",
    "your_secret", "replace-me", "replace_me", "changeme", "change_me",
    "placeholder", "example", "example-key", "example-token", "example-secret",
    "dummy", "redacted", "none", "null", "true", "false",
}


@dataclass(frozen=True)
class Finding:
    """Safe diagnostic metadata; no matched secret is retained."""

    path: str
    line: int
    category: str


def is_placeholder(value: str) -> bool:
    value = value.strip()
    normalized = value.lower()
    return (
        normalized in PLACEHOLDERS
        or bool(re.fullmatch(r"[xX*._-]+", value))
        or bool(re.fullmatch(r"<[^>]+>|\{[^}]+\}|\{\{.*\}\}", value))
        or bool(re.fullmatch(r"\$\{?[A-Za-z_][\w]*\}?|%[A-Za-z_][\w]*%", value))
        or bool(re.fullmatch(r"\$env:[A-Za-z_][\w]*|\$\{env:[A-Za-z_][\w]*\}", value, re.IGNORECASE))
        or bool(re.fullmatch(r"(?:your|replace|insert)[_-].+", value, re.IGNORECASE))
    )


def concrete_value(expression: str, *, config: bool, header: bool = False) -> bool:
    """Recognize literals; variable references and environment reads are safe."""
    expression = expression.lstrip(" \t")
    quoted = QUOTED_VALUE_PATTERN.match(expression)
    if quoted:
        value = quoted.group("value")
        if "f" in (quoted.group("prefix") or "").lower():
            try:
                literal = ast.parse(quoted.group(), mode="eval").body
            except SyntaxError:
                return False
            if not isinstance(literal, ast.JoinedStr) or any(
                isinstance(part, ast.FormattedValue) for part in literal.values
            ):
                return False
            value = "".join(part.value for part in literal.values)
    else:
        # Unquoted values must stay on their original source line.
        expression = expression.split("\n", 1)[0].strip()
        if header and re.match(r"(?:Bearer|Basic|Digest)\s+", expression, re.IGNORECASE):
            value = expression.split(" #", 1)[0].rstrip(",;").strip()
        elif re.fullmatch(r"[+-]?\d+(?:\.\d+)?\s*[,;}]?", expression):
            value = expression.rstrip(",;}").strip()
        elif config:
            value = expression.split(" #", 1)[0].strip().rstrip(",;")
            if re.search(r"(?:getenv|environ|process\.env|import\.meta\.env|\$env:)", value):
                return False
            if re.search(r"[()\[\]]", value):
                return False
        else:
            return False
    if header:
        parts = value.split(None, 1)
        if parts and parts[0].lower() in {"bearer", "basic", "digest"}:
            value = parts[1] if len(parts) > 1 else ""
    return not is_placeholder(value)


def read_text(path: Path) -> str | None:
    """Read UTF text; skip recognized binaries, NUL bytes, and binary controls."""
    if path.suffix.lower() in BINARY_SUFFIXES:
        return None
    contents = path.read_bytes()
    if contents.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return contents.decode("utf-32")
    if contents.startswith((b"\xff\xfe", b"\xfe\xff")):
        return contents.decode("utf-16")
    if b"\x00" in contents:
        return None
    if any(byte < 9 or 13 < byte < 32 for byte in contents):
        return None
    # ASCII credentials remain visible even in text saved in a legacy encoding.
    return contents.decode("utf-8-sig", errors="replace")


def scan_repository(root: Path) -> list[Finding]:
    """Scan tracked and untracked text, including local .env files and tests."""
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Repository directory does not exist: {root}")
    findings: list[Finding] = []
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        subdirectories[:] = sorted(
            name for name in subdirectories
            if name.lower() not in EXCLUDED_DIRECTORIES
            and not (Path(directory) / name).is_symlink()
        )
        for name in sorted(filenames):
            path = Path(directory) / name
            if path.is_symlink():
                continue
            contents = read_text(path)
            if contents is None:
                continue
            relative = path.relative_to(root).as_posix()
            config = path.suffix.lower() in CONFIG_SUFFIXES or name.lower().startswith(".env")
            offset = 0
            for line_number, line in enumerate(contents.splitlines(keepends=True), start=1):
                categories: set[str] = set()
                if KEY_PATTERN.search(line):
                    categories.add("key-prefix")
                if any(
                    concrete_value(contents[offset + match.end():], config=config)
                    for match in ASSIGNMENT_PATTERN.finditer(line)
                ):
                    categories.add("secret-assignment")
                if any(
                    concrete_value(contents[offset + match.end():], config=config, header=True)
                    for match in AUTHORIZATION_PATTERN.finditer(line)
                ):
                    categories.add("authorization-value")
                findings.extend(
                    Finding(relative, line_number, category)
                    for category in sorted(categories)
                )
                offset += len(line)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args(argv)
    try:
        findings = scan_repository(arguments.root)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Secret scan failed: {type(error).__name__}")
        return 2
    if findings:
        print("Potential hardcoded secrets found (matched values are hidden):")
        for finding in findings:
            print(f"  {finding.path}:{finding.line}: {finding.category}")
        print(f"Findings: {len(findings)}")
        return 1
    print("Secret scan passed: no likely hardcoded secrets found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
