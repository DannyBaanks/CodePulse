"""Comprehensive tests for the CodePulse code health scorecard tool."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from codepulse.ai_insights import QuickFix, generate_insights, generate_quick_fixes
from codepulse.analyzers import (
    analyze_complexity,
    analyze_dependencies,
    analyze_documentation,
    analyze_security,
    analyze_structure,
    analyze_testing,
)
from codepulse.cli import compute_scorecard as compute_cli_scorecard
from codepulse.cli import install_hook, run_analyzers
from codepulse.diff import format_diff
from codepulse.scorer import (
    WEIGHTS,
    DimensionScore,
    Scorecard,
    _clamp,
    _score_to_grade,
    compute_scorecard,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_scorecard(**dim_scores) -> Scorecard:
    """Helper to create a Scorecard for tests."""
    issues = {k: [] for k in dim_scores}
    return compute_scorecard(dim_scores, issues)


# ===========================================================================
# 1. Scorer tests
# ===========================================================================


class TestScorer:
    """Tests for the scoring engine."""

    def test_perfect_score(self):
        scores = {d: 100.0 for d in WEIGHTS}
        sc = compute_scorecard(scores)
        assert sc.overall_score == 100.0
        assert sc.overall_grade == "A"

    def test_zero_score(self):
        scores = {d: 0.0 for d in WEIGHTS}
        sc = compute_scorecard(scores)
        assert sc.overall_score == 0.0
        assert sc.overall_grade == "F"

    def test_mixed_scores(self):
        dim_scores = {
            "security": 80.0,
            "complexity": 60.0,
            "testing": 100.0,
            "documentation": 70.0,
            "dependencies": 90.0,
            "structure": 50.0,
        }
        sc = compute_scorecard(dim_scores)
        expected = sum(dim_scores[d] * WEIGHTS[d] for d in dim_scores)
        assert sc.overall_score == pytest.approx(expected, abs=0.01)
        assert 0.0 <= sc.overall_score <= 100.0

    def test_grade_boundaries(self):
        assert _score_to_grade(95) == "A"
        assert _score_to_grade(90) == "A"
        assert _score_to_grade(89.9) == "B"
        assert _score_to_grade(80) == "B"
        assert _score_to_grade(79.9) == "C"
        assert _score_to_grade(70) == "C"
        assert _score_to_grade(69.9) == "D"
        assert _score_to_grade(60) == "D"
        assert _score_to_grade(59.9) == "F"
        assert _score_to_grade(0) == "F"

    def test_grade_boundaries_computed(self):
        scores = {d: 85.0 for d in WEIGHTS}
        sc = compute_scorecard(scores)
        assert sc.overall_grade == "B"

        scores = {d: 75.0 for d in WEIGHTS}
        sc = compute_scorecard(scores)
        assert sc.overall_grade == "C"

        scores = {d: 65.0 for d in WEIGHTS}
        sc = compute_scorecard(scores)
        assert sc.overall_grade == "D"

    def test_summary_generation(self):
        sc = _make_scorecard(security=90, complexity=50)
        assert isinstance(sc.summary, str)
        assert len(sc.summary) > 0

    def test_summary_empty_dimensions(self):
        sc = compute_scorecard({})
        assert "Code health score" in sc.summary

    def test_summary_weak_dimension(self):
        sc = _make_scorecard(security=30, complexity=90)
        assert "Focus on improving security" in sc.summary

    def test_summary_strong_dimension(self):
        sc = _make_scorecard(security=95, complexity=95)
        assert "is a strength" in sc.summary

    def test_clamp(self):
        assert _clamp(-10) == 0.0
        assert _clamp(150) == 100.0
        assert _clamp(50) == 50.0

    def test_dimension_scores_populated(self):
        sc = _make_scorecard(security=80, complexity=60)
        assert "security" in sc.dimensions
        assert "complexity" in sc.dimensions
        assert sc.dimensions["security"].score == 80.0
        assert sc.dimensions["security"].grade == "B"

    def test_issues_attached(self):
        issues = {"security": ["found password"]}
        sc = compute_scorecard({"security": 50.0}, issues)
        assert sc.dimensions["security"].issues == ["found password"]

    def test_score_bounds(self):
        sc = _make_scorecard(security=200, complexity=-50)
        assert sc.overall_score <= 100.0
        assert sc.overall_score >= 0.0

    def test_partial_dimensions(self):
        sc = compute_scorecard({"security": 100.0})
        assert sc.overall_score == 100.0 * WEIGHTS["security"]


# ===========================================================================
# 2. Analyzer tests
# ===========================================================================


class TestSecurityAnalyzer:
    """Tests for the security analyzer."""

    def test_security_clean(self, tmp_path: Path):
        code = tmp_path / "clean.py"
        code.write_text("x = 1\n")
        score, _issues = analyze_security(tmp_path)
        assert score == 100.0
        assert _issues == []

    def test_security_hardcoded_secret(self, tmp_path: Path):
        code = tmp_path / "bad.py"
        code.write_text("password = 'abc123defghi'\n")
        score, issues = analyze_security(tmp_path)
        assert score < 100.0
        assert any("password" in i["message"].lower() for i in issues)

    def test_security_eval(self, tmp_path: Path):
        code = tmp_path / "unsafe.py"
        code.write_text("eval('1+1')\n")
        score, issues = analyze_security(tmp_path)
        assert score < 100.0
        assert any("eval()" in i["message"] for i in issues)

    def test_security_exec(self, tmp_path: Path):
        code = tmp_path / "unsafe.py"
        code.write_text("exec('pass')\n")
        score, issues = analyze_security(tmp_path)
        assert score < 100.0
        assert any("exec()" in i["message"] for i in issues)

    def test_security_os_system(self, tmp_path: Path):
        code = tmp_path / "run.py"
        code.write_text("os.system('ls')\n")
        score, issues = analyze_security(tmp_path)
        assert score < 100.0
        assert any("os.system()" in i["message"] for i in issues)

    def test_security_pickle(self, tmp_path: Path):
        code = tmp_path / "data.py"
        code.write_text("pickle.loads(b'x')\n")
        score, issues = analyze_security(tmp_path)
        assert score < 100.0
        assert any("pickle" in i["message"].lower() for i in issues)

    def test_security_skips_git_dir(self, tmp_path: Path):
        git_dir = tmp_path / ".git" / "hooks"
        git_dir.mkdir(parents=True)
        code = git_dir / "hook.py"
        code.write_text("password = 'abc123defghi'\n")
        score, _issues = analyze_security(tmp_path)
        assert score == 100.0


class TestComplexityAnalyzer:
    """Tests for the complexity analyzer."""

    def test_complexity_clean(self, tmp_path: Path):
        code = tmp_path / "simple.py"
        code.write_text("def add(a, b):\n    return a + b\n")
        score, issues = analyze_complexity(tmp_path)
        assert score == 100.0
        assert issues == []

    def test_complexity_complex(self, tmp_path: Path):
        # Create a function with high cyclomatic complexity using nested ifs
        lines = ["def complex_func(x):"]
        for i in range(25):
            lines.append(f"    if x > {i}:")
            lines.append("        x += 1")
        lines.append("    return x")
        code = tmp_path / "complex.py"
        code.write_text("\n".join(lines) + "\n")
        score, issues = analyze_complexity(tmp_path)
        assert score < 100.0
        assert len(issues) > 0

    def test_many_parameters(self, tmp_path: Path):
        code = tmp_path / "params.py"
        code.write_text("def func(a, b, c, d, e, f, g, h, i):\n    pass\n")
        _score, issues = analyze_complexity(tmp_path)
        assert any("parameters" in i["message"].lower() for i in issues)

    def test_long_file(self, tmp_path: Path):
        lines = [f"line_{i} = {i}" for i in range(501)]
        code = tmp_path / "long.py"
        code.write_text("\n".join(lines) + "\n")
        score, issues = analyze_complexity(tmp_path)
        assert score < 100.0
        assert any("lines" in i["message"].lower() for i in issues)


class TestTestingAnalyzer:
    """Tests for the testing analyzer."""

    def test_testing_with_tests(self, tmp_path: Path):
        src = tmp_path / "mymod.py"
        src.write_text("def add(a, b): return a + b\n")
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_mymod.py"
        test_file.write_text("import pytest\n\ndef test_add(): assert 1 + 1 == 2\n")
        score, _issues = analyze_testing(tmp_path)
        assert score >= 60

    def test_testing_no_tests(self, tmp_path: Path):
        src = tmp_path / "mymod.py"
        src.write_text("def add(a, b): return a + b\n")
        score, _issues = analyze_testing(tmp_path)
        assert score < 60


class TestDocumentationAnalyzer:
    """Tests for the documentation analyzer."""

    def test_documentation_with_readme(self, tmp_path: Path):
        readme = tmp_path / "README.md"
        readme.write_text("# My Project\n" + "x" * 200 + "\n")
        code = tmp_path / "mod.py"
        code.write_text('"""Module docstring."""\n')
        score, _issues = analyze_documentation(tmp_path)
        assert score > 0

    def test_documentation_no_readme(self, tmp_path: Path):
        code = tmp_path / "mod.py"
        code.write_text("x = 1\n")
        _score, issues = analyze_documentation(tmp_path)
        assert any("README" in i["message"] for i in issues)

    def test_documentation_short_readme(self, tmp_path: Path):
        readme = tmp_path / "README.md"
        readme.write_text("short\n")
        _score, issues = analyze_documentation(tmp_path)
        assert any("short" in i["message"].lower() for i in issues)


class TestDependenciesAnalyzer:
    """Tests for the dependencies analyzer."""

    def test_dependencies_pinned(self, tmp_path: Path):
        req = tmp_path / "requirements.txt"
        req.write_text("requests==2.28.0\nflask==2.3.0\n")
        score, _issues = analyze_dependencies(tmp_path)
        assert score == 100.0

    def test_dependencies_unpinned(self, tmp_path: Path):
        req = tmp_path / "requirements.txt"
        req.write_text("requests\nflask\n")
        score, issues = analyze_dependencies(tmp_path)
        assert score < 100.0
        assert any("Unpinned" in i["message"] for i in issues)

    def test_dependencies_problematic(self, tmp_path: Path):
        req = tmp_path / "requirements.txt"
        req.write_text("fabric2==1.0\n")
        _score, issues = analyze_dependencies(tmp_path)
        assert any("problematic" in i["message"].lower() for i in issues)

    def test_dependencies_none_found(self, tmp_path: Path):
        score, issues = analyze_dependencies(tmp_path)
        assert score < 100.0
        assert any("No dependency file" in i["message"] for i in issues)


class TestStructureAnalyzer:
    """Tests for the structure analyzer."""

    def test_structure_clean(self, tmp_path: Path):
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "mod.py").write_text("x = 1\n")
        (tmp_path / ".gitignore").write_text("__pycache__/\n")
        (tmp_path / "pyproject.toml").write_text('[project]\nname="test"\n')
        (tmp_path / "README.md").write_text("# Test\n")
        ci = tmp_path / ".github" / "workflows"
        ci.mkdir(parents=True)
        (ci / "ci.yml").write_text("name: CI\n")
        score, _issues = analyze_structure(tmp_path)
        assert score >= 80

    def test_structure_missing_init(self, tmp_path: Path):
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "mod.py").write_text("x = 1\n")
        _score, issues = analyze_structure(tmp_path)
        assert any("__init__.py" in i["message"] for i in issues)


# ===========================================================================
# 3. Integration tests
# ===========================================================================


class TestIntegration:
    """Integration tests for the full pipeline."""

    def test_full_pipeline(self, tmp_path: Path):
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "app.py").write_text(
            'def hello():\n    """Say hello."""\n    return "world"\n'
        )
        (tmp_path / "README.md").write_text("# My App\n" + "x" * 200 + "\n")
        (tmp_path / ".gitignore").write_text("__pycache__/\n")
        (tmp_path / "pyproject.toml").write_text('[project]\nname="myapp"\n')

        score_s, issues_s = analyze_security(tmp_path)
        score_c, issues_c = analyze_complexity(tmp_path)
        score_t, issues_t = analyze_testing(tmp_path)
        score_d, issues_d = analyze_documentation(tmp_path)
        score_dep, issues_dep = analyze_dependencies(tmp_path)
        score_st, issues_st = analyze_structure(tmp_path)

        all_issues = issues_s + issues_c + issues_t + issues_d + issues_dep + issues_st

        sc = compute_scorecard(
            {
                "security": score_s,
                "complexity": score_c,
                "testing": score_t,
                "documentation": score_d,
                "dependencies": score_dep,
                "structure": score_st,
            }
        )

        assert 0.0 <= sc.overall_score <= 100.0
        assert sc.overall_grade in ("A", "B", "C", "D", "F")
        assert isinstance(sc.summary, str)

        fixes = generate_quick_fixes(all_issues)
        assert isinstance(fixes, list)

        insights = generate_insights(sc, all_issues, "myapp")
        assert isinstance(insights, str)
        assert len(insights) > 0

    def test_cli_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "codepulse", "--help"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "codepulse" in result.stdout.lower()

    def test_cli_invalid_path(self):
        result = subprocess.run(
            [sys.executable, "-m", "codepulse", "/nonexistent/path/xyz"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0

    def test_config_applies_thresholds_and_exclusions(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.codepulse]\n"
            "max_file_lines = 1\n"
            "exclude_patterns = ['ignored.py']\n"
            "weights = { security = 1.0, complexity = 0.0, testing = 0.0, documentation = 0.0, dependencies = 0.0, structure = 0.0 }\n"
        )
        (tmp_path / "app.py").write_text("x = 1\ny = 2\n")
        (tmp_path / "ignored.py").write_text("password = 'abc123defghi'\n")

        results = run_analyzers(tmp_path)
        _, scorecard = compute_cli_scorecard(results)

        assert any("(>1)" in issue["message"] for issue in scorecard["issues"])
        assert not any(issue["file"] == "ignored.py" for issue in scorecard["issues"])
        assert scorecard["overall_score"] == scorecard["dimensions"]["security"]["score"]

    def test_install_hook_rejects_non_git_directory(self, tmp_path: Path):
        assert install_hook(tmp_path) == 1


# ===========================================================================
# 4. AI insights tests
# ===========================================================================


class TestAIInsights:
    """Tests for AI insights module."""

    def test_quick_fixes(self):
        issues = [
            {"severity": "critical", "message": "Use of eval()", "file": "app.py", "line": 5},
            {"severity": "high", "message": "hardcoded password in config", "file": "cfg.py", "line": 1},
            {"severity": "low", "message": "Function 'foo' missing docstring", "file": "bar.py", "line": 10},
        ]
        fixes = generate_quick_fixes(issues)
        assert isinstance(fixes, list)
        assert len(fixes) > 0
        assert all(isinstance(f, QuickFix) for f in fixes)
        assert all(f.fix for f in fixes)

    def test_quick_fixes_empty(self):
        fixes = generate_quick_fixes([])
        assert fixes == []

    def test_insights_without_ai(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        sc = _make_scorecard(security=80, complexity=60)
        issues = [{"severity": "medium", "message": "test issue", "file": "x.py", "line": 1}]
        result = generate_insights(sc, issues, "test-repo")
        assert isinstance(result, str)
        assert "test-repo" in result
        assert len(result) > 0


# ===========================================================================
# 5. Determinism tests
# ===========================================================================


class TestDeterminism:
    """Tests to verify deterministic behavior."""

    def test_same_fixture_same_scores(self, tmp_path: Path):
        """Running analysis twice on same repo should produce identical scores."""
        # Create a deterministic fixture
        pkg = tmp_path / "deterministic_pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "module.py").write_text(
            'def add(a, b):\n    """Add two numbers."""\n    return a + b\n'
            + '\n' * 100  # Add some lines
        )
        (tmp_path / "README.md").write_text("# Test\n" + "x" * 100 + "\n")
        (tmp_path / ".gitignore").write_text("__pycache__/\n")
        (tmp_path / "pyproject.toml").write_text('[project]\nname="test"\n')

        # Run first scan
        results1 = {}
        for analyzer_name, analyzer in [
            ("security", analyze_security),
            ("complexity", analyze_complexity),
            ("testing", analyze_testing),
            ("documentation", analyze_documentation),
            ("dependencies", analyze_dependencies),
            ("structure", analyze_structure),
        ]:
            score, issues = analyzer(tmp_path)
            results1[analyzer_name] = {"score": score, "issues": issues}

        sc1 = compute_scorecard(
            {k: v["score"] for k, v in results1.items()},
            {k: v["issues"] for k, v in results1.items()},
        )

        # Run second scan (same fixture, fresh process would be ideal but this tests
        # that the analysis is deterministic within the same process)
        results2 = {}
        for analyzer_name, analyzer in [
            ("security", analyze_security),
            ("complexity", analyze_complexity),
            ("testing", analyze_testing),
            ("documentation", analyze_documentation),
            ("dependencies", analyze_dependencies),
            ("structure", analyze_structure),
        ]:
            score, issues = analyzer(tmp_path)
            results2[analyzer_name] = {"score": score, "issues": issues}

        sc2 = compute_scorecard(
            {k: v["score"] for k, v in results2.items()},
            {k: v["issues"] for k, v in results2.items()},
        )

        # Scores should be identical
        assert sc1.overall_score == sc2.overall_score, f"Overall score differs: {sc1.overall_score} != {sc2.overall_score}"
        assert sc1.overall_grade == sc2.overall_grade

        # Dimension scores should be identical
        for dim in results1:
            assert results1[dim]["score"] == results2[dim]["score"], f"Dimension {dim} score differs"

        # Issue counts should be identical
        for dim in results1:
            assert len(results1[dim]["issues"]) == len(results2[dim]["issues"]), f"Dimension {dim} issue count differs"

    def test_json_output_deterministic(self, tmp_path: Path):
        """JSON output should be identical across runs."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "main.py").write_text("x = 1\n")

        import json
        import os
        import subprocess

        # Run twice via CLI with proper PYTHONPATH
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).parent.parent)

        result1 = subprocess.run(
            [sys.executable, "-m", "codepulse", "scan", str(tmp_path), "--json", "--no-ai"],
            capture_output=True, text=True, cwd=tmp_path.parent, env=env, check=False
        )
        result2 = subprocess.run(
            [sys.executable, "-m", "codepulse", "scan", str(tmp_path), "--json", "--no-ai"],
            capture_output=True, text=True, cwd=tmp_path.parent, env=env, check=False
        )

        assert result1.returncode == 0, f"First run failed: {result1.stderr}"
        assert result2.returncode == 0, f"Second run failed: {result2.stderr}"

        # Extract JSON from stdout (find the first '{' character)
        def extract_json(output: str):
            idx = output.find('{')
            if idx >= 0:
                return json.loads(output[idx:])
            raise ValueError("No JSON found in output")

        data1 = extract_json(result1.stdout)
        data2 = extract_json(result2.stdout)

        # Overall score should be identical
        assert data1["scorecard"]["overall_score"] == data2["scorecard"]["overall_score"]
        assert data1["scorecard"]["overall_grade"] == data2["scorecard"]["overall_grade"]

        # All dimension scores should match
        for dim in data1["scorecard"]["dimensions"]:
            assert data1["scorecard"]["dimensions"][dim]["score"] == data2["scorecard"]["dimensions"][dim]["score"]
            assert data1["scorecard"]["dimensions"][dim]["grade"] == data2["scorecard"]["dimensions"][dim]["grade"]


def test_diff_summary_uses_overall_delta():
    """The summary must not use the last per-dimension delta."""
    before = Scorecard(
        dimensions={"alpha": DimensionScore(0, "F"), "zeta": DimensionScore(100, "A")},
        overall_score=50,
        overall_grade="F",
        summary="",
    )
    after = Scorecard(
        dimensions={"alpha": DimensionScore(100, "A"), "zeta": DimensionScore(0, "F")},
        overall_score=60,
        overall_grade="D",
        summary="",
    )

    assert "Score improved by 10.0 points" in format_diff(before, after)
