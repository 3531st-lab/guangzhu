"""Repository checks use assembled fake samples, never real credentials."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    spec = spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


loc = load_script("loc")
check_secrets = load_script("check_secrets")


def write(root: Path, name: str, contents: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def assignment(name: str, value: str, *, quote: bool = True) -> str:
    delimiters = '"' if quote else ""
    return name + " = " + delimiters + value + delimiters + "\n"


def fake_value() -> str:
    return "synthetic" + "Credential" + "987654321"


def test_loc_counts_nonblank_lines_and_groups(tmp_path: Path) -> None:
    write(tmp_path, "backend/guangzhu/example.py", "# comment\n\nvalue = 1\n")
    write(tmp_path, "scripts/example.ps1", "Write-Output 1\n")
    write(tmp_path, "start.cmd", "@echo off\n")
    write(tmp_path, "README.md", "Documentation is not code.\n")
    assert loc.count_lines(tmp_path) == {".": 1, "backend": 2, "scripts": 1}


@pytest.mark.parametrize("name", [
    "tests/example.py", "backend/test_example.py", "backend/example_test.py",
    ".venv/example.py", "node_modules/example.js", "data/cache/example.py",
    "generated/example.py", "frontend/example.generated.ts", "frontend/app.min.js",
    "frontend/example.test.tsx", "frontend/example.spec.jsx",
])
def test_loc_excludes_tests_and_generated_paths(tmp_path: Path, name: str) -> None:
    write(tmp_path, name, "value = 1\n")
    assert loc.count_lines(tmp_path) == {}


def test_loc_excludes_generated_header(tmp_path: Path) -> None:
    write(tmp_path, "backend/example.py", "# " + "auto-" + "generated\nvalue = 1\n")
    assert loc.count_lines(tmp_path) == {}


def test_loc_excludes_documentation_data_reports_and_reviews(tmp_path: Path) -> None:
    for directory in ("docs", "data", "reports", "reviews"):
        write(tmp_path, f"{directory}/nested/reference.html", "<p>reference</p>\n")
    write(tmp_path, "backend/product.py", "value = 1\n")
    assert loc.count_lines(tmp_path) == {"backend": 1}


def test_scanner_detects_key_prefix_and_safe_metadata(tmp_path: Path) -> None:
    value = "sk" + "-" + "A1" * 11
    write(tmp_path, "sample.txt", value + "\n")
    findings = check_secrets.scan_repository(tmp_path)
    assert [(item.path, item.line, item.category) for item in findings] == [
        ("sample.txt", 1, "key-prefix"),
    ]
    assert value not in repr(findings)


@pytest.mark.parametrize("name", ["api_key", "TOKEN", "secret"])
def test_scanner_detects_literal_assignments(tmp_path: Path, name: str) -> None:
    write(tmp_path, "sample.py", assignment(name, fake_value()))
    assert {item.category for item in check_secrets.scan_repository(tmp_path)} == {
        "secret-assignment",
    }


@pytest.mark.parametrize("prefix", ["r", "b", "u", "f", "br", "rb", "fr", "rf", "R", "F"])
@pytest.mark.parametrize("quote", ['"', "'", '"' * 3, "'" * 3])
def test_scanner_detects_prefixed_python_literals(tmp_path: Path, prefix: str, quote: str) -> None:
    expression = prefix + quote + fake_value() + quote
    write(tmp_path, "sample.py", assignment("api_key", expression, quote=False))
    assert [(item.line, item.category) for item in check_secrets.scan_repository(tmp_path)] == [
        (1, "secret-assignment"),
    ]


@pytest.mark.parametrize("prefix", ["", "r", "b", "u", "f", "fr", "rf"])
@pytest.mark.parametrize("quote", ['"' * 3, "'" * 3])
@pytest.mark.parametrize("name", ["api_key", "Authorization"])
def test_scanner_detects_multiline_literals(
    tmp_path: Path, prefix: str, quote: str, name: str,
) -> None:
    value = ("Bearer " if name == "Authorization" else "") + fake_value()
    expression = prefix + quote + "\n" + value + "\n" + quote
    write(tmp_path, "sample.py", "# fixture\n" + assignment(name, expression, quote=False))
    category = "authorization-value" if name == "Authorization" else "secret-assignment"
    assert [(item.path, item.line, item.category) for item in check_secrets.scan_repository(tmp_path)] == [
        ("sample.py", 2, category),
    ]


@pytest.mark.parametrize("prefix", ["r", "b", "u", "f", "fr", "rf"])
def test_scanner_detects_prefixed_authorization(tmp_path: Path, prefix: str) -> None:
    expression = prefix + '"Bearer ' + fake_value() + '"'
    write(tmp_path, "request.py", assignment("Authorization", expression, quote=False))
    assert {item.category for item in check_secrets.scan_repository(tmp_path)} == {
        "authorization-value",
    }


@pytest.mark.parametrize("prefix", ["f", "fr", "rf", "F"])
@pytest.mark.parametrize("quote", ['"', '"' * 3])
def test_scanner_ignores_prefixed_fstring_interpolation(
    tmp_path: Path, prefix: str, quote: str,
) -> None:
    expression = prefix + quote + fake_value() + "{incoming_key}" + quote
    write(tmp_path, "sample.py", assignment("api_key", expression, quote=False))
    header = prefix + quote + "Bearer {incoming_key}" + quote
    write(tmp_path, "request.py", assignment("Authorization", header, quote=False))
    assert check_secrets.scan_repository(tmp_path) == []


def test_scanner_treats_escaped_fstring_braces_as_literal(tmp_path: Path) -> None:
    expression = 'f"' + fake_value() + '{{literal}}"'
    write(tmp_path, "sample.py", assignment("api_key", expression, quote=False))
    assert {item.category for item in check_secrets.scan_repository(tmp_path)} == {
        "secret-assignment",
    }


def test_scanner_does_not_merge_following_config_lines(tmp_path: Path) -> None:
    contents = assignment("token", "${TOKEN}", quote=False) + "MODE = demo\n"
    contents += assignment("Authorization", "Bearer {token}", quote=False) + "MODE = demo\n"
    write(tmp_path, ".env", contents)
    assert check_secrets.scan_repository(tmp_path) == []


def test_scanner_detects_json_and_unquoted_env_values(tmp_path: Path) -> None:
    contents = '{"' + "api_key" + '": "' + fake_value() + '"}\n'
    write(tmp_path, "sample.json", contents)
    write(tmp_path, ".env", assignment("token", fake_value(), quote=False))
    assert {item.path for item in check_secrets.scan_repository(tmp_path)} == {
        "sample.json", ".env",
    }


def test_scanner_detects_typed_assignment_and_later_dict_value(tmp_path: Path) -> None:
    typed = "api_key" + ': str = "' + fake_value() + '"\n'
    mapping = '{"' + "api_key" + '": incoming_key, "' + "token" + '": "' + fake_value() + '"}\n'
    write(tmp_path, "sample.py", typed + mapping)
    assert [item.line for item in check_secrets.scan_repository(tmp_path)] == [1, 2]


def test_scanner_detects_indexed_header_and_shell_assignment(tmp_path: Path) -> None:
    header = 'headers["' + "Authorization" + '"] = "Bearer ' + fake_value() + '"\n'
    write(tmp_path, "request.py", header)
    write(tmp_path, "sample.sh", assignment("TOKEN", fake_value(), quote=False))
    assert {item.category for item in check_secrets.scan_repository(tmp_path)} == {
        "authorization-value", "secret-assignment",
    }


@pytest.mark.parametrize("scheme", ["Bearer", "Basic"])
def test_scanner_detects_authorization(tmp_path: Path, scheme: str) -> None:
    contents = '{"' + "Authorization" + '": "' + scheme + " " + fake_value() + '"}\n'
    write(tmp_path, "request.py", contents)
    assert {item.category for item in check_secrets.scan_repository(tmp_path)} == {
        "authorization-value",
    }


@pytest.mark.parametrize("value", [
    "", "YOUR_API_KEY", "<API_KEY>", "${TOKEN}", "%TOKEN%", "...", "REPLACE_ME",
    "$env:TOKEN", "${env:TOKEN}",
])
def test_scanner_ignores_placeholders(tmp_path: Path, value: str) -> None:
    write(tmp_path, "sample.py", assignment("api_key", value))
    contents = "Authorization" + ': "Bearer ' + value + '"\n'
    write(tmp_path, "request.txt", contents)
    assert check_secrets.scan_repository(tmp_path) == []


@pytest.mark.parametrize("expression", [
    'os.getenv("API_KEY")', 'os.environ["API_KEY"]', 'os.environ.get("API_KEY")',
    "process.env.API_KEY", "$env:API_KEY", "incoming_key",
])
def test_scanner_ignores_runtime_values(tmp_path: Path, expression: str) -> None:
    write(tmp_path, "sample.py", assignment("api_key", expression, quote=False))
    contents = "Authorization" + ': f"Bearer {token}"\n'
    write(tmp_path, "request.py", contents)
    assert check_secrets.scan_repository(tmp_path) == []


def test_scanner_ignores_unquoted_environment_placeholders(tmp_path: Path) -> None:
    write(tmp_path, ".env", assignment("token", "${TOKEN}", quote=False))
    write(tmp_path, "request.txt", "Authorization" + ": Bearer {token}\n")
    assert check_secrets.scan_repository(tmp_path) == []


def test_scanner_ignores_descriptions(tmp_path: Path) -> None:
    description = (
        "Detect a prefix made of sk and a hyphen followed by 20 alphanumeric characters.\n"
        "Detect concrete assignments to api_key, token, and secret.\n"
        "Detect an HTTP Authorization header with a concrete value.\n"
        "token: str\n"
    )
    write(tmp_path, "task.md", description)
    assert check_secrets.scan_repository(tmp_path) == []


@pytest.mark.parametrize("directory", [".git", ".venv", "node_modules", "data/cache", "__pycache__"])
def test_scanner_excludes_caches(tmp_path: Path, directory: str) -> None:
    write(tmp_path, directory + "/sample.txt", assignment("secret", fake_value()))
    assert check_secrets.scan_repository(tmp_path) == []


def test_scanner_skips_binaries_and_reads_utf16(tmp_path: Path) -> None:
    (tmp_path / "sample.bin").write_bytes(b"\x00" + assignment("secret", fake_value()).encode())
    (tmp_path / "sample.txt").write_bytes(assignment("secret", fake_value()).encode("utf-16"))
    findings = check_secrets.scan_repository(tmp_path)
    assert [item.path for item in findings] == ["sample.txt"]


def test_scanner_cli_redacts_values_and_returns_failure(tmp_path: Path) -> None:
    value = fake_value()
    write(tmp_path, "sample.py", assignment("secret", value))
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_secrets.py"), "--root", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1
    assert "sample.py:1" in result.stdout
    assert value not in result.stdout + result.stderr


def test_scanner_cli_passes_clean_directory(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_secrets.py"), "--root", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
