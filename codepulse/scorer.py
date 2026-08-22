"""Core scoring engine for CodePulse.

Takes dimension analysis results and produces grades (A-F) and an
overall health score (0-100) using configurable weights.
"""

from dataclasses import dataclass, field

from .config import get_weights

# Backward-compatible export
WEIGHTS = get_weights()

GRADE_THRESHOLDS = [
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (0, "F"),
]


@dataclass
class DimensionScore:
    """Score for a single analysis dimension."""

    score: float
    grade: str = ""
    issues: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)  # Why this score?


@dataclass
class Scorecard:
    """Complete scoring result with per-dimension grades, evidence, and overall score."""

    dimensions: dict[str, DimensionScore]
    overall_score: float
    overall_grade: str
    summary: str


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp a numeric value to the given range."""
    return max(low, min(high, value))


def _score_to_grade(score: float) -> str:
    """Convert a numeric score to a letter grade."""
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def _generate_evidence(dim_name: str, score: float, issues: list[dict]) -> list[str]:
    """Generate human-readable evidence for a dimension score."""
    evidence: list[str] = []

    # Base assessment
    if score >= 90:
        evidence.append(f"[+] {dim_name.title()} is excellent ({score:.0f}/100)")
    elif score >= 80:
        evidence.append(f"[+] {dim_name.title()} is good ({score:.0f}/100)")
    elif score >= 60:
        evidence.append(f"[~] {dim_name.title()} needs improvement ({score:.0f}/100)")
    else:
        evidence.append(f"[-] {dim_name.title()} is poor ({score:.0f}/100)")

    # Specific evidence from issues
    if issues:
        critical = sum(1 for i in issues if isinstance(i, dict) and i.get("severity") == "critical")
        high = sum(1 for i in issues if isinstance(i, dict) and i.get("severity") == "high")
        medium = sum(1 for i in issues if isinstance(i, dict) and i.get("severity") == "medium")
        low = sum(1 for i in issues if isinstance(i, dict) and i.get("severity") == "low")

        if critical:
            evidence.append(f"  {critical} critical issue(s) found")
        if high:
            evidence.append(f"  {high} high-severity issue(s)")
        if medium:
            evidence.append(f"  {medium} medium-severity issue(s)")
        if low:
            evidence.append(f"  {low} low-severity issue(s)")

        # Specific issue types for key dimensions
        if dim_name == "security":
            for issue in issues:
                if isinstance(issue, dict) and "password" in issue.get("message", "").lower():
                    evidence.append(f"  Hardcoded credential detected: {issue.get('file', '')}:{issue.get('line', '')}")
        elif dim_name == "complexity":
            for issue in issues:
                if isinstance(issue, dict) and "complexity" in issue.get("message", "").lower():
                    evidence.append(f"  {issue.get('message', '')} at {issue.get('file', '')}:{issue.get('line', '')}")

    return evidence


def generate_summary(overall_score: float, overall_grade: str, dimensions: dict[str, DimensionScore]) -> str:
    """Return a 1-2 sentence human-readable summary of the scorecard.

    Identifies the strongest and weakest dimensions to give actionable context.
    """
    if not dimensions:
        return f"Code health score: {overall_score:.0f}/100 (grade {overall_grade})."

    sorted_dims = sorted(dimensions.items(), key=lambda item: item[1].score)
    weakest_name, weakest = sorted_dims[0]
    strongest_name, strongest = sorted_dims[-1]

    parts = [
        f"Overall score: {overall_score:.0f}/100 (grade {overall_grade}).",
    ]

    if weakest.score < 70:
        parts.append(f"Focus on improving {weakest_name} ({weakest.score:.0f}, grade {weakest.grade}).")
    elif strongest.score >= 90:
        parts.append(f"{strongest_name} is a strength ({strongest.score:.0f}, grade {strongest.grade}).")

    return " ".join(parts)


def compute_scorecard(
    dimension_scores: dict[str, float],
    dimension_issues: dict[str, list[dict]] | None = None,
    weights: dict[str, float] | None = None,
) -> Scorecard:
    """Compute a full scorecard from raw dimension scores.

    Args:
        dimension_scores: Mapping of dimension name to numeric score (0-100).
            Valid keys: security, complexity, testing, documentation,
            dependencies, structure.
        dimension_issues: Optional mapping of dimension name to a list of
            issue descriptions found during analysis.

    Returns:
        A Scorecard dataclass with per-dimension grades, overall weighted
        score, overall grade, and a human-readable summary.
    """
    dimension_issues = dimension_issues or {}
    dimensions: dict[str, DimensionScore] = {}

    for name, raw_score in dimension_scores.items():
        clamped = _clamp(raw_score)
        grade = _score_to_grade(clamped)
        issues = dimension_issues.get(name, [])
        evidence = _generate_evidence(name, clamped, issues)
        dimensions[name] = DimensionScore(score=clamped, grade=grade, issues=issues, evidence=evidence)

    weights = weights or get_weights()
    overall_score = 0.0
    for name, weight in weights.items():
        if name in dimensions:
            overall_score += dimensions[name].score * weight

    overall_score = _clamp(overall_score)
    overall_grade = _score_to_grade(overall_score)
    summary = generate_summary(overall_score, overall_grade, dimensions)

    return Scorecard(
        dimensions=dimensions,
        overall_score=overall_score,
        overall_grade=overall_grade,
        summary=summary,
    )
