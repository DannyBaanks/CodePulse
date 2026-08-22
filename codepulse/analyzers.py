"""Code analysis modules for CodePulse.

Each analyzer scans a repository directory and returns a numeric score (0-100)
plus a list of issues found.
"""

import ast
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEVERITY_WEIGHTS = {"critical": 15, "high": 10, "medium": 5, "low": 2}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp a numeric value to the given range."""
    return max(lo, min(hi, value))


def _python_files(repo: Path):
    """Yield all .py files under *repo*, skipping common non‑source dirs."""
    skip = {".git", "__pycache__", ".tox", ".eggs", "node_modules", ".mypy_cache"}
    for p in repo.rglob("*.py"):
        if any(part in skip for part in p.parts):
            continue
        yield p


def _safe_read(path: Path) -> str:
    """Return file text or empty string on read errors."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _is_test_file(path: Path) -> bool:
    """Check if a file is in a test directory or has test naming pattern."""
    parts = path.parts
    return any(part in {"tests", "test", "test_"} for part in parts) or path.name.startswith("test_")


def _parse_ast(path: Path):
    """Return an AST module or *None* on parse failure."""
    source = _safe_read(path)
    if not source:
        return None
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError:
        return None


# ---------------------------------------------------------------------------
# 1. Security
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    (re.compile(r"""(?i)(api[_\-]?key|apikey)\s*[:=]\s*['"][A-Za-z0-9_\-]{16,}['"]"""), "Possible hardcoded API key"),
    (re.compile(r"""(?i)(password|passwd|pwd)\s*[:=]\s*['"][^'"]{6,}['"]"""), "Possible hardcoded password"),
    (re.compile(r"""(?i)(secret|token)\s*[:=]\s*['"][A-Za-z0-9_\-\.]{16,}['"]"""), "Possible hardcoded secret/token"),
    (re.compile(r"""(?i)aws[_\-]?secret[_\-]?access[_\-]?key\s*[:=]\s*['"][A-Za-z0-9/+]{30,}['"]"""), "Possible AWS secret key"),
    (re.compile(r"""(?i)(bearer)\s+[A-Za-z0-9_\-\.]{20,}"""), "Possible hardcoded bearer token"),
]

# AST node types for unsafe calls
_UNSAFE_FUNC_NAMES = {"eval", "exec"}
_UNSAFE_ATTR_NAMES = {"system"}

_SQL_INJECTION = [
    (re.compile(r"""(?i)(execute|cursor\.execute)\s*\(\s*['"].*%s"""), "String formatting in SQL execute"),
    (re.compile(r"""(?i)(execute|cursor\.execute)\s*\(\s*f['"]"""), "f-string in SQL execute"),
    (re.compile(r"""(?i)(execute|cursor\.execute)\s*\(\s*['"].*\+"""), "String concatenation in SQL execute"),
    (re.compile(r"""(?i)(execute|cursor\.execute)\s*\(\s*['"].*\.format"""), ".format() in SQL execute"),
]


def _is_eval_or_exec(node: ast.Call) -> str | None:
    """Return the unsafe function name if this is an eval/exec call."""
    if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
        return node.func.id
    return None


def _is_pickle_call(node: ast.Call) -> bool:
    """Return True if this is a pickle.loads/load call."""
    if isinstance(node.func, ast.Attribute):
        return (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id == "pickle"
            and node.func.attr in {"loads", "load"}
        )
    return False


def _is_subprocess_shell_true(node: ast.Call) -> bool:
    """Return True if this is subprocess.run/call/Popen with shell=True."""
    if (
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
        and node.func.attr in {"run", "call", "Popen"}
    ):
        for kw in node.keywords:
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                return True
    return False


def _is_os_system(node: ast.Call) -> bool:
    """Return True if this is os.system() call."""
    if isinstance(node.func, ast.Attribute):
        return (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.func.attr == "system"
        )
    return False


def _check_unsafe_calls(tree: ast.AST, filepath: str, rel: str, issues: list[dict]) -> None:
    """Walk AST and detect actual unsafe function calls (not string literals)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            unsafe = _is_eval_or_exec(node)
            if unsafe:
                issues.append({"severity": "high", "message": f"Use of {unsafe}()", "file": rel, "line": node.lineno})
            elif _is_pickle_call(node):
                issues.append({"severity": "high", "message": "Use of pickle deserialization", "file": rel, "line": node.lineno})
            elif _is_subprocess_shell_true(node):
                issues.append({"severity": "high", "message": "subprocess with shell=True", "file": rel, "line": node.lineno})
            elif _is_os_system(node):
                issues.append({"severity": "high", "message": "Use of os.system()", "file": rel, "line": node.lineno})


def analyze_security(repo_path: Path) -> tuple[float, list[dict]]:
    """Detect hardcoded secrets and unsafe code patterns using AST.

    Returns (score, issues) where score is 0‑100.
    """
    try:
        issues: list[dict] = []
        repo = Path(repo_path)

        for py in _python_files(repo):
            rel = str(py.relative_to(repo))
            source = _safe_read(py)
            lines = source.splitlines()

            # 1. Secret patterns (line-based, but skip comments/docstrings roughly)
            is_test = _is_test_file(py)
            secret_severity = "high" if is_test else "critical"
            for lineno, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for pat, msg in _SECRET_PATTERNS:
                    if pat.search(line):
                        issues.append({"severity": secret_severity, "message": msg, "file": rel, "line": lineno})

            # 2. AST-based unsafe call detection (no false positives from strings)
            tree = _parse_ast(py)
            if tree is not None:
                _check_unsafe_calls(tree, source, rel, issues)

            # 3. SQL injection patterns (line-based, could be improved with AST)
            for lineno, line in enumerate(lines, 1):
                for pat, msg in _SQL_INJECTION:
                    if pat.search(line):
                        issues.append({"severity": "critical", "message": msg, "file": rel, "line": lineno})

        penalty = sum(_SEVERITY_WEIGHTS[i["severity"]] for i in issues)
        score = _clamp(100 - penalty)
        return score, issues
    except (OSError, SyntaxError, ValueError) as e:
        return 0.0, [{"severity": "low", "message": f"Security analysis failed: {e}", "file": "", "line": 0}]


# ---------------------------------------------------------------------------
# 2. Complexity
# ---------------------------------------------------------------------------

def _cyclomatic_complexity(node: ast.AST) -> int:
    """Compute cyclomatic complexity for a single function/method AST node."""
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            complexity += 1 + len(child.ifs)
    return complexity


def analyze_complexity(repo_path: Path) -> tuple[float, list[dict]]:
    """Measure cyclomatic complexity and file/function size.

    Returns (score, issues) where score is 0‑100.
    """
    try:
        issues: list[dict] = []
        repo = Path(repo_path)
        complexities: list[int] = []

        for py in _python_files(repo):
            rel = str(py.relative_to(repo))
            source = _safe_read(py)
            lines = source.splitlines()
            if len(lines) > 500:
                issues.append({"severity": "medium", "message": f"File has {len(lines)} lines (>500)", "file": rel, "line": 1})

            tree = _parse_ast(py)
            if tree is None:
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cc = _cyclomatic_complexity(node)
                    complexities.append(cc)
                    if cc > 10:
                        sev = "high" if cc > 20 else "medium"
                        issues.append({"severity": sev, "message": f"Function '{node.name}' has complexity {cc}", "file": rel, "line": node.lineno})
                    args = len(node.args.args) + len(node.args.posonlyargs) + len(node.args.kwonlyargs)
                    if node.args.vararg:
                        args += 1
                    if node.args.kwarg:
                        args += 1
                    if args > 7:
                        issues.append({"severity": "low", "message": f"Function '{node.name}' has {args} parameters (>7)", "file": rel, "line": node.lineno})

        avg = sum(complexities) / len(complexities) if complexities else 0
        penalty = 0.0
        if avg > 5:
            penalty += (avg - 5) * 4
        penalty += len([i for i in issues if i["severity"] == "high"]) * 5
        penalty += len([i for i in issues if i["severity"] == "medium"]) * 2
        score = _clamp(100 - penalty)
        return score, issues
    except (OSError, SyntaxError, ValueError) as e:
        return 0.0, [{"severity": "low", "message": f"Complexity analysis failed: {e}", "file": "", "line": 0}]


# ---------------------------------------------------------------------------
# 3. Testing
# ---------------------------------------------------------------------------

_TEST_DIRS = {"tests", "test", "spec", "specs"}
_TEST_FILE_RE = re.compile(r"(?:test_.+|.+_test)\.py$", re.IGNORECASE)
_TEST_IMPORTS = {"pytest", "unittest", "mock", "unittest.mock"}


def _has_test_imports(tree: ast.AST) -> bool:
    """Return True if the AST contains pytest/unittest imports."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _TEST_IMPORTS:
                    return True
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] in _TEST_IMPORTS
        ):
            return True
    return False


def analyze_testing(repo_path: Path) -> tuple[float, list[dict]]:
    """Evaluate test coverage and infrastructure.

    Returns (score, issues) where score is 0‑100.
    """
    try:
        issues: list[dict] = []
        repo = Path(repo_path)

        source_files = 0
        test_files = 0
        has_test_dir = False
        has_test_imports = False

        for py in _python_files(repo):
            name = py.name
            rel = str(py.relative_to(repo))
            parts = set(py.relative_to(repo).parts)

            if _TEST_FILE_RE.search(name):
                test_files += 1
                if not parts.intersection(_TEST_DIRS):
                    issues.append({"severity": "low", "message": f"Test file '{name}' not in a test directory", "file": rel, "line": 1})
            else:
                source_files += 1

            if parts.intersection(_TEST_DIRS):
                has_test_dir = True

            if not has_test_imports:
                tree = _parse_ast(py)
                if tree and _has_test_imports(tree):
                    has_test_imports = True

        if not has_test_dir:
            issues.append({"severity": "medium", "message": "No dedicated test directory found", "file": "", "line": 0})
        if not has_test_imports:
            issues.append({"severity": "medium", "message": "No pytest/unittest imports found", "file": "", "line": 0})

        ratio = test_files / max(source_files, 1)
        score = 0.0
        if ratio >= 0.4:
            score = 100
        elif ratio >= 0.25:
            score = 90
        elif ratio >= 0.15:
            score = 80
        elif ratio >= 0.05:
            score = 60
        elif ratio > 0:
            score = 40
        else:
            score = 10
            issues.append({"severity": "high", "message": "No test files found", "file": "", "line": 0})

        if not has_test_dir:
            score -= 5
        if not has_test_imports:
            score -= 5

        score = _clamp(score)
        return score, issues
    except (OSError, SyntaxError, ValueError) as e:
        return 0.0, [{"severity": "low", "message": f"Testing analysis failed: {e}", "file": "", "line": 0}]


# ---------------------------------------------------------------------------
# 4. Documentation
# ---------------------------------------------------------------------------

def _has_docstring(node: ast.AsyncFunctionDef | ast.FunctionDef | ast.ClassDef | ast.Module) -> bool:
    """Return True if the AST node has a docstring."""
    return ast.get_docstring(node) is not None


def _iter_functions_and_classes(tree: ast.AST):
    """Yield all FunctionDef, AsyncFunctionDef, and ClassDef nodes in the AST, including nested ones."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node


def analyze_documentation(repo_path: Path) -> tuple[float, list[dict]]:
    """Assess README, docstrings, and type‑hint coverage.

    Returns (score, issues) where score is 0‑100.
    """
    try:
        issues: list[dict] = []
        repo = Path(repo_path)

        # README
        readme = None
        for name in ("README.md", "README.rst", "README.txt", "README"):
            if (repo / name).is_file():
                readme = repo / name
                break

        if readme is None:
            issues.append({"severity": "high", "message": "No README file found", "file": "", "line": 0})
        else:
            content = _safe_read(readme)
            if len(content.strip()) < 100:
                issues.append({"severity": "medium", "message": "README is very short (<100 chars)", "file": readme.name, "line": 1})

        total_funcs = 0
        documented_funcs = 0
        total_classes = 0
        documented_classes = 0
        total_params = 0
        typed_params = 0

        for py in _python_files(repo):
            rel = str(py.relative_to(repo))
            tree = _parse_ast(py)
            if tree is None:
                continue

            for node in _iter_functions_and_classes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    total_funcs += 1
                    if _has_docstring(node):
                        documented_funcs += 1
                    else:
                        issues.append({"severity": "low", "message": f"Function '{node.name}' missing docstring", "file": rel, "line": node.lineno})

                    for arg in node.args.args:
                        if arg.arg == "self" or arg.arg == "cls":
                            continue
                        total_params += 1
                        if arg.annotation is not None:
                            typed_params += 1

                elif isinstance(node, ast.ClassDef):
                    total_classes += 1
                    if _has_docstring(node):
                        documented_classes += 1
                    else:
                        issues.append({"severity": "low", "message": f"Class '{node.name}' missing docstring", "file": rel, "line": node.lineno})

        func_pct = (documented_funcs / max(total_funcs, 1)) * 100
        class_pct = (documented_classes / max(total_classes, 1)) * 100
        type_pct = (typed_params / max(total_params, 1)) * 100

        score = func_pct * 0.4 + class_pct * 0.3 + type_pct * 0.3
        if readme:
            score += 10
        else:
            score -= 10

        score = _clamp(score)
        return score, issues
    except (OSError, SyntaxError, ValueError) as e:
        return 0.0, [{"severity": "low", "message": f"Documentation analysis failed: {e}", "file": "", "line": 0}]


# ---------------------------------------------------------------------------
# 5. Dependencies
# ---------------------------------------------------------------------------

_KNOWN_PROBLEMATIC = {"fabric2", "fabric", "sudo", "pycrypto", "pycrypto2"}

_PINNED_RE = re.compile(r"^[A-Za-z0-9_\-]+(.txt|\.toml|\.cfg)?(?===)")


def analyze_dependencies(repo_path: Path) -> tuple[float, list[dict]]:
    """Audit dependency files for hygiene.

    Returns (score, issues) where score is 0‑100.
    """
    try:
        issues: list[dict] = []
        repo = Path(repo_path)
        score = 100.0

        dep_files_found = False

        # requirements.txt
        req = repo / "requirements.txt"
        if req.is_file():
            dep_files_found = True
            rel = "requirements.txt"
            for lineno, line in enumerate(req.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                line = line.strip()
                if not line or line.startswith(("#", "-")):
                    continue
                pkg = re.split(r"[>=<~!]", line)[0].strip().lower()
                if pkg in _KNOWN_PROBLEMATIC:
                    issues.append({"severity": "medium", "message": f"Potentially problematic package: {pkg}", "file": rel, "line": lineno})
                if "==" not in line:
                    issues.append({"severity": "low", "message": f"Unpinned dependency: {line}", "file": rel, "line": lineno})
                    score -= 2

        # pyproject.toml
        pyproject = repo / "pyproject.toml"
        if pyproject.is_file():
            dep_files_found = True
            content = pyproject.read_text(encoding="utf-8", errors="replace")
            in_deps = False
            for lineno, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped == "dependencies = [":
                    in_deps = True
                    continue
                if in_deps:
                    if stripped == "]":
                        in_deps = False
                        continue
                    pkg_match = re.match(r'["\']([A-Za-z0-9_\-]+)', stripped)
                    if pkg_match:
                        pkg = pkg_match.group(1).lower()
                        if pkg in _KNOWN_PROBLEMATIC:
                            issues.append({"severity": "medium", "message": f"Potentially problematic package: {pkg}", "file": "pyproject.toml", "line": lineno})

        # setup.py
        setup_py = repo / "setup.py"
        if setup_py.is_file():
            dep_files_found = True

        if not dep_files_found:
            issues.append({"severity": "medium", "message": "No dependency file found (requirements.txt / pyproject.toml / setup.py)", "file": "", "line": 0})
            score -= 30

        score = _clamp(score)
        return score, issues
    except (OSError, SyntaxError, ValueError) as e:
        return 0.0, [{"severity": "low", "message": f"Dependency analysis failed: {e}", "file": "", "line": 0}]


# ---------------------------------------------------------------------------
# 6. Structure
# ---------------------------------------------------------------------------

def analyze_structure(repo_path: Path) -> tuple[float, list[dict]]:
    """Evaluate project scaffolding and packaging.

    Returns (score, issues) where score is 0‑100.
    """
    try:
        issues: list[dict] = []
        repo = Path(repo_path)
        score = 0.0

        # __init__.py presence in source packages
        py_dirs = set()
        for py in _python_files(repo):
            py_dirs.add(py.parent)

        missing_init = [d for d in py_dirs if not (d / "__init__.py").is_file() and d != repo]
        if missing_init:
            for d in missing_init[:5]:
                issues.append({"severity": "low", "message": f"Missing __init__.py in {d.relative_to(repo)}", "file": "", "line": 0})
        else:
            score += 25

        # .gitignore
        if (repo / ".gitignore").is_file():
            score += 15
        else:
            issues.append({"severity": "medium", "message": "No .gitignore file", "file": "", "line": 0})

        # setup.py / pyproject.toml
        if (repo / "pyproject.toml").is_file() or (repo / "setup.py").is_file():
            score += 25
        else:
            issues.append({"severity": "medium", "message": "No setup.py or pyproject.toml", "file": "", "line": 0})

        # CI config
        ci_dir = repo / ".github" / "workflows"
        if ci_dir.is_dir() and any(ci_dir.iterdir()):
            score += 20
        else:
            issues.append({"severity": "low", "message": "No CI configuration found (.github/workflows)", "file": "", "line": 0})

        # README (bonus)
        if any((repo / name).is_file() for name in ("README.md", "README.rst", "README.txt", "README")):
            score += 15
        else:
            issues.append({"severity": "low", "message": "No README file", "file": "", "line": 0})

        score = _clamp(score)
        return score, issues
    except (OSError, SyntaxError, ValueError) as e:
        return 0.0, [{"severity": "low", "message": f"Structure analysis failed: {e}", "file": "", "line": 0}]
