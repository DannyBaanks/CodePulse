"""Build the self-contained interactive CodePulse HTML report."""

import base64
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_THEME = {
    "dark_background": "#0d1117",
    "light_background": "#ffffff",
    "accent": "#58a6ff",
}

REPORT_SECTIONS = ("score", "dimensions", "findings", "insights", "quick_fixes")


def build_html(scorecard: dict[str, Any], insights: dict[str, Any], repo_name: str) -> str:
    """Materialize a portable report with no server or external assets required."""
    template_path = Path(__file__).parent / "templates" / "scorecard.html"
    template = template_path.read_text(encoding="utf-8")
    score = float(scorecard.get("overall_score", 0))
    grade = str(scorecard.get("overall_grade", "N/A"))
    score_class = "grade-a" if score >= 80 else "grade-b" if score >= 50 else "grade-c" if score >= 30 else "grade-f"
    logo_path = Path(__file__).parent.parent / "assets" / "logo.png"
    logo_base64 = base64.b64encode(logo_path.read_bytes()).decode("ascii") if logo_path.exists() else ""

    dimensions = "".join(_dimension_html(name, data) for name, data in scorecard.get("dimensions", {}).items())
    issues = _issues_html(scorecard.get("issues_by_category", {}))
    ai_summary = str(insights.get("summary", ""))
    ai_html = (
        "<div class='section ai-insights'><h2>AI Insights</h2><div class='ai-content'>"
        f"{html.escape(ai_summary).replace(chr(10), '<br>')}</div></div>"
        if ai_summary else ""
    )
    fixes_html = _fixes_html(insights.get("quick_fixes", []))
    payload = json.dumps({"scorecard": scorecard, "insights": insights}, default=str).replace("</", "<\\/")

    replacements = {
        "repo_name": html.escape(repo_name), "overall_score": f"{score:.1f}", "overall_grade": html.escape(grade),
        "score_class": score_class, "score_deg": f"{score * 3.6:.1f}deg", "dimensions": dimensions,
        "issues": issues or "<p class='no-issues'>No issues found!</p>", "ai_insights": ai_html,
        "quick_fixes": fixes_html, "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "logo_base64": logo_base64, "report_payload": payload,
    }
    for key, value in replacements.items():
        template = template.replace("{{ " + key + " }}", value)
    return template


def _dimension_html(name: str, data: dict[str, Any]) -> str:
    score = float(data.get("score", 0))
    return (
        "<div class='dimension'><div class='dim-header'>"
        f"<span class='dim-name'>{html.escape(name.capitalize())}</span>"
        f"<span class='dim-score'>{score:.0f}/100</span>"
        f"<span class='dim-grade'>{html.escape(str(data.get('grade', 'N/A')))}</span>"
        f"</div><div class='dim-bar'><div class='dim-fill' style='width: {score}%'></div></div></div>"
    )


def _issues_html(issues_by_category: dict[str, list[dict[str, Any]]]) -> str:
    sections = []
    for category, issues in issues_by_category.items():
        if not issues:
            continue
        rows = []
        for issue in issues:
            severity = str(issue.get("severity", "low"))
            location = f"{issue.get('file', '')}:{issue.get('line', '')}" if issue.get("file") else ""
            evidence = [f"Message: {html.escape(str(issue.get('message', '')))}"]
            if location:
                evidence.append(f"Location: {html.escape(location)}")
            evidence.append(f"Category: {html.escape(str(issue.get('category', category)))}")
            rows.append(
                f"<li class='issue severity-{html.escape(severity)}'><div class='issue-header'>"
                f"<span class='sev-badge'>{html.escape(severity.upper())}</span>"
                f"<span class='issue-message'>{html.escape(str(issue.get('message', '')))}</span>"
                f"<span class='file-info'>{html.escape(location)}</span>"
                "<button class='evidence-toggle' type='button'>Show evidence</button>"
                "<button class='copy-btn' type='button' title='Copy finding'>Copy</button>"
                f"</div><div class='issue-evidence'>{'<br>'.join(evidence)}</div></li>"
            )
        sections.append(f"<h3>{html.escape(category.capitalize())}</h3><ul class='issues'>{''.join(rows)}</ul>")
    return "".join(sections)


def _fixes_html(quick_fixes: list[dict[str, Any]]) -> str:
    if not quick_fixes:
        return "<!-- No quick fixes available. -->"
    rows = []
    for fix in quick_fixes:
        effort = html.escape(str(fix.get("effort", "medium")))
        rows.append(
            f"<li class='effort-{effort}'><span class='effort-badge'>{effort.upper()}</span> "
            f"<strong>{html.escape(str(fix.get('issue', '')))}</strong>: {html.escape(str(fix.get('fix', '')))}</li>"
        )
    return "<div class='section quick-fixes'><h2>Quick Fixes</h2><ul class='fixes'>" + "".join(rows) + "</ul></div>"
