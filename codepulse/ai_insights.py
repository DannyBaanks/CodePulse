"""AI-powered insights for CodePulse.

Takes analysis results from the scorer module and generates human-readable
recommendations. Uses OpenAI (gpt-4o-mini) when an API key is available,
otherwise falls back to rule-based insights.
"""

from __future__ import annotations

import os
import textwrap
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scorer import Scorecard

try:
    from openai import OpenAI, OpenAIError

    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------


@dataclass
class QuickFix:
    """A suggested fix for a single issue."""

    issue: str
    fix: str
    effort: str  # "low" | "medium" | "high"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_insights(
    scorecard: Scorecard,
    all_issues: list[dict],
    repo_name: str,
) -> str:
    """Generate a markdown-formatted insights report.

    Attempts to call OpenAI (gpt-4o-mini) when ``OPENAI_API_KEY`` is set in
    the environment.  Falls back to a rule-based report on any failure.

    Args:
        scorecard: The ``Scorecard`` produced by :func:`scorer.compute_scorecard`.
        all_issues: Flat list of issue dicts from every analyzer.
        repo_name: Name of the repository being analysed.

    Returns:
        A markdown string with actionable insights (under 500 words when
        generated via OpenAI).
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if _OPENAI_AVAILABLE and api_key:
        try:
            return _generate_ai_insights(scorecard, all_issues, repo_name)
        except OpenAIError:
            return _generate_rule_based_insights(scorecard, all_issues, repo_name)
    return _generate_rule_based_insights(scorecard, all_issues, repo_name)


def generate_quick_fixes(issues: list[dict]) -> list[QuickFix]:
    """Suggest a concrete fix for each issue when possible.

    Args:
        issues: Flat list of issue dicts from every analyzer.

    Returns:
        A list of :class:`QuickFix` instances, one per issue that has a
        known remediation.
    """
    fixes: list[QuickFix] = []
    for issue in issues:
        quick = _suggest_fix(issue)
        if quick is not None:
            fixes.append(quick)
    return fixes


# ---------------------------------------------------------------------------
# OpenAI path
# ---------------------------------------------------------------------------


def _build_prompt(
    scorecard: Scorecard,
    all_issues: list[dict],
    repo_name: str,
) -> str:
    """Build the system+user prompt for OpenAI."""
    dim_lines = []
    for name, dim in scorecard.dimensions.items():
        dim_lines.append(f"- {name}: {dim.score:.0f}/100 (grade {dim.grade})")
    dimensions_text = "\n".join(dim_lines)

    top_issues = sorted(all_issues, key=lambda i: _severity_rank(i.get("severity", "low")), reverse=True)[:10]
    issue_lines = []
    for iss in top_issues:
        loc = f"{iss.get('file', '')}:{iss.get('line', '')}" if iss.get("file") else "n/a"
        issue_lines.append(f"- [{iss.get('severity', 'low')}] {iss.get('message', '')} ({loc})")
    issues_text = "\n".join(issue_lines) if issue_lines else "- No issues found."

    return textwrap.dedent(f"""\
        You are a code-quality advisor. Given the analysis of a repository called
        "{repo_name}", provide actionable insights in markdown.

        ## Scores
        {dimensions_text}
        Overall: {scorecard.overall_score:.0f}/100 (grade {scorecard.overall_grade})

        ## Top issues
        {issues_text}

        Provide:
        1. **Top 3 things to fix first** (prioritised by impact).
        2. **One thing the project does well** (a positive highlight).
        3. **Risk assessment** – what is most likely to cause problems in production?

        Keep the entire response under 500 words. Use markdown headings and bullet points.
    """)


def _generate_ai_insights(
    scorecard: Scorecard,
    all_issues: list[dict],
    repo_name: str,
) -> str:
    """Call OpenAI and return the markdown response."""
    client = OpenAI()
    prompt = _build_prompt(scorecard, all_issues, repo_name)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior software engineer who reviews codebases "
                    "and provides concise, actionable advice."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=1024,
        temperature=0.3,
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------

_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _severity_rank(severity: str) -> int:
    """Return numeric rank for severity (higher = worse)."""
    return _SEVERITY_RANK.get(severity, 0)


def _get_top_issues(all_issues: list[dict], limit: int = 3) -> list[dict]:
    """Get top N unique issues by severity."""
    sorted_issues = sorted(all_issues, key=lambda i: _severity_rank(i.get("severity", "low")), reverse=True)
    seen: set[str] = set()
    top: list[dict] = []
    for iss in sorted_issues:
        msg = iss.get("message", "")
        if msg not in seen:
            seen.add(msg)
            top.append(iss)
        if len(top) >= limit:
            break
    return top


def _get_strengths(scorecard: Scorecard) -> list[str]:
    """Get list of strengths (dimensions scoring >= 80)."""
    return [n for n, d in scorecard.dimensions.items() if d.score >= 80]


def _get_weak_dimensions(scorecard: Scorecard) -> list[str]:
    """Get list of weak dimensions (scoring < 60)."""
    return [n for n, d in scorecard.dimensions.items() if d.score < 60]


def _build_top_fix_lines(top_issues: list[dict]) -> list[str]:
    """Format top issues as markdown list."""
    if not top_issues:
        return ["No critical issues found."]
    lines = []
    for idx, iss in enumerate(top_issues, 1):
        loc = f" (`{iss.get('file', '')}:{iss.get('line', '')}`)" if iss.get("file") else ""
        lines.append(f"{idx}. **[{iss.get('severity', 'low').upper()}]** {iss.get('message', '')}{loc}")
    return lines


def _build_strength_lines(strengths: list[str], scorecard: Scorecard) -> list[str]:
    """Format strengths as markdown list."""
    if not strengths:
        return ["- The project has a complete analysis pipeline, which is a good starting point for improvement."]
    lines = []
    for name in strengths:
        dim = scorecard.dimensions[name]
        lines.append(f"- **{name.title()}** scored {dim.score:.0f}/100 (grade {dim.grade})")
    return lines


def _build_risk_lines(critical_count: int, high_count: int, weak_dims: list[str]) -> list[str]:
    """Format risk assessment as markdown list."""
    lines = []
    if critical_count:
        lines.append(
            f"- **High risk:** {critical_count} critical issue(s) detected. "
            "These should be addressed before any release."
        )
    if high_count:
        lines.append(
            f"- **Elevated risk:** {high_count} high-severity issue(s) found. "
            "Consider prioritising these in the next sprint."
        )
    if weak_dims:
        lines.append(
            f"- **Weak dimensions:** {', '.join(weak_dims)}. "
            "Technical debt is accumulating in these areas."
        )
    if not critical_count and not high_count and not weak_dims:
        lines.append("- Overall risk is low. The codebase appears healthy across all dimensions.")
    return lines


def _generate_rule_based_insights(
    scorecard: Scorecard,
    all_issues: list[dict],
    repo_name: str,
) -> str:
    """Build a markdown report without calling any external API."""
    lines: list[str] = [f"# Insights for {repo_name}\n"]
    lines.append(f"**Overall score:** {scorecard.overall_score:.0f}/100 ({scorecard.overall_grade})\n")

    # Top 3 things to fix
    lines.append("## Top 3 things to fix\n")
    lines.extend(_build_top_fix_lines(_get_top_issues(all_issues)))

    # Positive highlight
    lines.append("\n## What the project does well\n")
    lines.extend(_build_strength_lines(_get_strengths(scorecard), scorecard))

    # Risk assessment
    lines.append("\n## Risk assessment\n")
    critical_count = sum(1 for i in all_issues if i.get("severity") == "critical")
    high_count = sum(1 for i in all_issues if i.get("severity") == "high")
    lines.extend(_build_risk_lines(critical_count, high_count, _get_weak_dimensions(scorecard)))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Quick-fix suggestions
# ---------------------------------------------------------------------------

_FIX_RULES: list[tuple[str, str, str]] = [
    # (substring in message, fix description, effort)
    ("hardcoded API key", "Move the API key to an environment variable or secrets manager.", "low"),
    ("hardcoded password", "Move the password to an environment variable or secrets manager.", "low"),
    ("hardcoded secret", "Move the secret to an environment variable or secrets manager.", "low"),
    ("hardcoded bearer", "Move the bearer token to an environment variable or secrets manager.", "low"),
    ("Use of eval()", "Replace eval() with a safe alternative (e.g., ast.literal_eval for data, or a dedicated parser).", "medium"),
    ("Use of exec()", "Replace exec() with a safer alternative such as importlib or direct function calls.", "high"),
    ("Use of pickle", "Replace pickle with a safer serialization format such as JSON or msgpack.", "medium"),
    ("subprocess with shell=True", "Set shell=False and pass arguments as a list instead of a string.", "medium"),
    ("Use of os.system()", "Replace os.system() with subprocess.run() for better error handling and security.", "medium"),
    ("String formatting in SQL", "Use parameterised queries instead of string formatting in SQL.", "medium"),
    ("f-string in SQL", "Use parameterised queries instead of f-strings in SQL.", "medium"),
    ("String concatenation in SQL", "Use parameterised queries instead of string concatenation in SQL.", "medium"),
    (".format() in SQL", "Use parameterised queries instead of .format() in SQL.", "medium"),
    ("complexity", "Break the function into smaller, single-responsibility functions.", "medium"),
    ("parameters", "Reduce the number of parameters by grouping related values into a dataclass or dict.", "low"),
    ("lines", "Split the file into smaller modules organised by responsibility.", "high"),
    ("No test files found", "Add unit tests using pytest or unittest.", "medium"),
    ("No dedicated test directory", "Create a 'tests/' directory and move test files there.", "low"),
    ("No pytest/unittest imports", "Add a test framework (pytest recommended) and write initial tests.", "medium"),
    ("No README file", "Add a README.md with project description, installation, and usage instructions.", "low"),
    ("README is very short", "Expand the README with setup instructions, examples, and API docs.", "low"),
    ("missing docstring", "Add a docstring describing the purpose, parameters, and return value.", "low"),
    ("No .gitignore file", "Add a .gitignore to exclude common Python artifacts (pycache, .venv, etc.).", "low"),
    ("No setup.py or pyproject.toml", "Add a pyproject.toml with project metadata and dependencies.", "medium"),
    ("No CI configuration", "Add a GitHub Actions workflow for linting, testing, and optionally releasing.", "medium"),
    ("Unpinned dependency", "Pin the dependency to a specific version (e.g., package==1.2.3).", "low"),
    ("Potentially problematic package", "Review the dependency for known vulnerabilities or better alternatives.", "medium"),
    ("Security analysis failed", "Investigate the cause; the codebase may have syntax errors or unusual structure.", "low"),
    ("Complexity analysis failed", "Investigate the cause; files may contain syntax that cannot be parsed.", "low"),
    ("Testing analysis failed", "Investigate the cause; check for import errors or missing test framework.", "low"),
    ("Documentation analysis failed", "Investigate the cause; check for encoding issues or broken files.", "low"),
    ("Dependency analysis failed", "Ensure dependency files are valid and readable.", "low"),
    ("Structure analysis failed", "Ensure the repository path is correct and accessible.", "low"),
]


def _suggest_fix(issue: dict) -> QuickFix | None:
    """Return a :class:`QuickFix` if a known remediation exists, else ``None``."""
    message = issue.get("message", "")
    for pattern, fix, effort in _FIX_RULES:
        if pattern in message:
            return QuickFix(issue=message, fix=fix, effort=effort)
    return None
