"""CodePulse CLI: deterministic code health scorecard with optional AI prioritization."""

import argparse
import json
import sys
from datetime import timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .scorer import Scorecard

BANNER = r"""
   ____          _        ____
  / ___|___   __| | ___  / ___|  ___ __ _ _ __  _ __   ___ _ __
 | |   / _ \ / _` |/ _ \| |  _ / __/ _` | '_ \| '_ \ / _ \ '__|
 | |__| (_) | (_| |  __/| |_| || (_| (_| | | | | | | |  __/ |
  \____\___/ \__,_|\___| \____|\___\__,_|_| |_|_| |_|\___|_|
          Deterministic Code Health Scorecard + Optional AI
"""


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    # Check for global help first (only if no subcommand)
    has_subcommand = len(sys.argv) > 1 and sys.argv[1] in {"scan", "diff", "install-hook"}
    
    # Check for help on specific subcommand: codepulse <subcommand> -h/--help
    if len(sys.argv) >= 3 and sys.argv[1] in {"scan", "diff", "install-hook"} and sys.argv[2] in ("-h", "--help"):
        _print_help(sys.argv[1])
        sys.exit(0)
    
    # Check for global help (only when no subcommand)
    if not has_subcommand and ("-h" in sys.argv or "--help" in sys.argv):
        _print_help()
        sys.exit(0)
    
    if has_subcommand:
        # Standard parsing with subcommands
        parser = argparse.ArgumentParser(
            prog="codepulse",
            description="Deterministic code health scorecard with optional AI prioritization.",
            epilog="Example: codepulse . --output report.html --format html",
        )
        subparsers = parser.add_subparsers(dest="command", help="Available commands", required=False)
        
        # Scan command (default)
        scan_parser = subparsers.add_parser("scan", help="Scan a repository (default)", add_help=False)
        scan_parser.add_argument(
            "repo_path",
            nargs="?",
            default=".",
            help="Path to the repository to analyze (default: current directory)",
        )
        scan_parser.add_argument("--output", "-o", default=None, help="Output file path")
        scan_parser.add_argument("--format", "-f", choices=["text", "html"], default="text", help="Output format")
        scan_parser.add_argument("--open", action="store_true", dest="auto_open", help="Auto-open HTML in browser")
        scan_parser.add_argument("--json", action="store_true", help="Output raw JSON")
        scan_parser.add_argument("--no-ai", action="store_true", help="Skip AI insights")
        scan_parser.add_argument("-h", "--help", action="store_true", help="Show this help message and exit")

        # Diff command
        diff_parser = subparsers.add_parser("diff", help="Compare scores between two commits", add_help=False)
        diff_parser.add_argument("ref1", help="First commit/ref (e.g., HEAD~1)")
        diff_parser.add_argument("ref2", help="Second commit/ref (e.g., HEAD)")
        diff_parser.add_argument("repo_path", nargs="?", default=".", help="Repository path")
        diff_parser.add_argument("-h", "--help", action="store_true", help="Show this help message and exit")

        # Install hook command
        hook_parser = subparsers.add_parser("install-hook", help="Install pre-commit hook", add_help=False)
        hook_parser.add_argument("repo_path", nargs="?", default=".", help="Repository path")
        hook_parser.add_argument("-h", "--help", action="store_true", help="Show this help message and exit")

        args = parser.parse_args()
        
        # Handle help for subcommands
        if getattr(args, 'help', False):
            _print_help(args.command)
            sys.exit(0)
            
        return args
    else:
        # No subcommand provided - backward compatibility: assume scan
        # Parse as scan with all args
        parser = argparse.ArgumentParser(
            prog="codepulse",
            description="Deterministic code health scorecard with optional AI prioritization.",
            epilog="Example: codepulse . --output report.html --format html",
            add_help=False,
        )
        parser.add_argument(
            "repo_path",
            nargs="?",
            default=".",
            help="Path to the repository to analyze (default: current directory)",
        )
        parser.add_argument("--output", "-o", default=None, help="Output file path")
        parser.add_argument("--format", "-f", choices=["text", "html"], default="text", help="Output format")
        parser.add_argument("--open", action="store_true", dest="auto_open", help="Auto-open HTML in browser")
        parser.add_argument("--json", action="store_true", help="Output raw JSON")
        parser.add_argument("--no-ai", action="store_true", help="Skip AI insights")
        parser.add_argument("-h", "--help", action="store_true", help="Show this help message and exit")
        
        args = parser.parse_args()
        args.command = "scan"
        return args


def _print_help(command=None):
    """Print help message."""
    if command == "scan":
        parser = argparse.ArgumentParser(prog="codepulse scan", add_help=False)
        parser.add_argument("repo_path", nargs="?", default=".", help="Path to the repository to analyze")
        parser.add_argument("--output", "-o", default=None, help="Output file path")
        parser.add_argument("--format", "-f", choices=["text", "html"], default="text", help="Output format")
        parser.add_argument("--open", action="store_true", dest="auto_open", help="Auto-open HTML in browser")
        parser.add_argument("--json", action="store_true", help="Output raw JSON")
        parser.add_argument("--no-ai", action="store_true", help="Skip AI insights")
        parser.print_help()
    elif command == "diff":
        parser = argparse.ArgumentParser(prog="codepulse diff", add_help=False)
        parser.add_argument("ref1", help="First commit/ref (e.g., HEAD~1)")
        parser.add_argument("ref2", help="Second commit/ref (e.g., HEAD)")
        parser.add_argument("repo_path", nargs="?", default=".", help="Repository path")
        parser.print_help()
    elif command == "install-hook":
        parser = argparse.ArgumentParser(prog="codepulse install-hook", add_help=False)
        parser.add_argument("repo_path", nargs="?", default=".", help="Repository path")
        parser.print_help()
    else:
        # Main help
        parser = argparse.ArgumentParser(prog="codepulse", add_help=False)
        parser.description = "Deterministic code health scorecard with optional AI prioritization."
        parser.epilog = "Example: codepulse . --output report.html --format html"
        subparsers = parser.add_subparsers(dest="command", help="Available commands")
        
        scan_parser = subparsers.add_parser("scan", help="Scan a repository (default)", add_help=False)
        scan_parser.add_argument("repo_path", nargs="?", default=".", help="Path to the repository to analyze (default: current directory)")
        
        diff_parser = subparsers.add_parser("diff", help="Compare scores between two commits", add_help=False)
        diff_parser.add_argument("ref1", help="First commit/ref (e.g., HEAD~1)")
        diff_parser.add_argument("ref2", help="Second commit/ref (e.g., HEAD)")
        diff_parser.add_argument("repo_path", nargs="?", default=".", help="Repository path")
        
        hook_parser = subparsers.add_parser("install-hook", help="Install pre-commit hook", add_help=False)
        hook_parser.add_argument("repo_path", nargs="?", default=".", help="Repository path")
        
        parser.print_help()


def validate_repo_path(repo_path: str) -> Path:
    """Validate and resolve the repository path."""
    path = Path(repo_path).resolve()
    if not path.exists():
        print(f"Error: Path does not exist: {path}", file=sys.stderr)
        sys.exit(1)
    if not path.is_dir():
        print(f"Error: Not a directory: {path}", file=sys.stderr)
        sys.exit(1)
    return path


def show_progress(message: str) -> None:
    """Display a progress message."""
    print(f"  [*] {message}...")


def run_analyzers(repo_path: Path, config: dict[str, Any] | None = None) -> dict:
    """Run all code analyzers and return collected results."""
    from codepulse.analyzers import (
        analyze_complexity,
        analyze_dependencies,
        analyze_documentation,
        analyze_security,
        analyze_structure,
        analyze_testing,
    )

    if config is None:
        from codepulse.config import load_config

        config = load_config(repo_path)

    analyzers = [
        ("security", "Analyzing security vulnerabilities", analyze_security),
        ("complexity", "Analyzing code complexity", analyze_complexity),
        ("testing", "Analyzing test signals", analyze_testing),
        ("documentation", "Analyzing documentation quality", analyze_documentation),
        ("dependencies", "Analyzing dependencies", analyze_dependencies),
        ("structure", "Analyzing project structure", analyze_structure),
    ]

    results = {}
    all_issues = []

    for analyzer_name, message, analyzer_func in analyzers:
        show_progress(message)
        try:
            score, issues = analyzer_func(repo_path, config)
            results[analyzer_name] = score
            for issue in issues:
                issue["category"] = analyzer_name
            all_issues.extend(issues)
        except OSError as e:
            print(f"  [!] Error in '{analyzer_name}' analyzer: {e}")
            results[analyzer_name] = 0.0
        except ValueError as e:
            print(f"  [!] Error in '{analyzer_name}' analyzer: {e}")
            results[analyzer_name] = 0.0
        except RuntimeError as e:
            print(f"  [!] Error in '{analyzer_name}' analyzer: {e}")
            results[analyzer_name] = 0.0

    return {"scores": results, "issues": all_issues, "config": config}


def compute_scorecard(results: dict):
    """Compute the overall scorecard from analysis results."""
    from codepulse.scorer import compute_scorecard as compute_sc

    scores = results["scores"]
    issues = results["issues"]

    # Build dimension scores dict
    dim_scores = {}
    for name, score in scores.items():
        dim_scores[name] = score

    # Group issues by category for evidence
    dim_issues: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        cat = issue.get("category", "unknown")
        if cat not in dim_issues:
            dim_issues[cat] = []
        dim_issues[cat].append(issue)

    # Compute scorecard with issues for evidence
    from codepulse.config import get_weights

    sc = compute_sc(dim_scores, dim_issues, weights=get_weights(results.get("config")))

    # Group issues by category
    issues_by_cat: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        cat = issue.get("category", "unknown")
        if cat not in issues_by_cat:
            issues_by_cat[cat] = []
        issues_by_cat[cat].append(issue)

    # Return both the Scorecard object and the dict representation
    scorecard_dict = {
        "overall_score": sc.overall_score,
        "overall_grade": sc.overall_grade,
        "summary": sc.summary,
        "dimensions": {k: {"score": v.score, "grade": v.grade, "issues": v.issues, "evidence": v.evidence} for k, v in sc.dimensions.items()},
        "issues": issues,
        "issues_by_category": issues_by_cat,
    }
    return sc, scorecard_dict


def generate_ai_insights(scorecard: "Scorecard", issues: list[dict], repo_name: str, no_ai: bool) -> dict:
    """Generate AI-powered insights about the codebase."""
    if no_ai:
        return {"summary": "AI insights skipped (--no-ai flag).", "recommendations": [], "quick_fixes": []}

    try:
        from codepulse.ai_insights import generate_insights, generate_quick_fixes
        insights = generate_insights(scorecard, issues, repo_name)
        quick_fixes = generate_quick_fixes(issues)
        return {
            "summary": insights,
            "recommendations": [],  # extracted from insights
            "quick_fixes": [{"issue": qf.issue, "fix": qf.fix, "effort": qf.effort} for qf in quick_fixes],
        }
    except ImportError:
        print("  [!] AI insights unavailable: OpenAI package not installed")
        return {"summary": "AI insights unavailable.", "recommendations": [], "quick_fixes": []}
    except RuntimeError as e:
        print(f"  [!] AI insights unavailable: {e}")
        return {"summary": "AI insights unavailable.", "recommendations": [], "quick_fixes": []}


def _score_color(score: float) -> str:
    """Return ANSI color code for a score."""
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    if score >= 80:
        return GREEN
    elif score >= 50:
        return YELLOW
    return RED


def _severity_style(severity: str) -> tuple[str, str]:
    """Return (ANSI color, short label) for a severity level."""
    RED = "\033[91m"
    YELLOW = "\033[93m"
    if severity == "critical":
        return RED, "CRIT"
    if severity == "high":
        return RED, "HIGH"
    if severity == "medium":
        return YELLOW, "MED"
    return "\033[94m", "LOW"


def format_text_report(scorecard: dict, insights: dict) -> str:
    """Format the results as a clean text report with ANSI colors."""
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    lines = []
    lines.append("")
    lines.append(f"{BOLD}{CYAN}{'=' * 60}{RESET}")
    lines.append(f"{BOLD}{CYAN}  CODEPULSE - Code Health Scorecard{RESET}")
    lines.append(f"{BOLD}{CYAN}{'=' * 60}{RESET}")
    lines.append("")

    score = scorecard.get("overall_score", 0)
    grade = scorecard.get("overall_grade", "N/A")
    s_color = _score_color(score)

    lines.append(f"  {BOLD}Overall Score:{RESET}  {s_color}{BOLD}{score:.1f}/100{RESET}")
    lines.append(f"  {BOLD}Grade:{RESET}          {s_color}{BOLD}{grade}{RESET}")
    lines.append("")

    lines.append(f"  {BOLD}Category Breakdown:{RESET}")
    dims = scorecard.get("dimensions", {})
    for cat, data in dims.items():
        cat_score = data.get("score", 0)
        cat_grade = data.get("grade", "N/A")
        c_color = _score_color(cat_score)
        bar_len = int(cat_score / 5)
        bar = "#" * bar_len + "-" * (20 - bar_len)
        lines.append(f"    {c_color}{cat.capitalize():15}{RESET} {bar} {c_color}{cat_score:.0f}/100 ({cat_grade}){RESET}")

    lines.append("")

    # Evidence / Why this score?
    dims = scorecard.get("dimensions", {})
    if any(d.get("evidence") for d in dims.values()):
        lines.append(f"  {BOLD}Why these scores?{RESET}")
        for cat, data in dims.items():
            evidence = data.get("evidence", [])
            if evidence:
                c_color = _score_color(data.get("score", 0))
                lines.append(f"    {c_color}{cat.capitalize()}:{RESET}")
                for ev in evidence:
                    lines.append(f"      {ev}")
        lines.append("")

    # Issues by severity
    issues = scorecard.get("issues", [])
    if issues:
        lines.append(f"  {BOLD}Issues Found ({len(issues)}):{RESET}")
        for cat, cat_issues in scorecard.get("issues_by_category", {}).items():
            if not cat_issues:
                continue
            lines.append(f"    {BOLD}{cat.capitalize()}:{RESET}")
            for issue in cat_issues:
                sev_color, sev_icon = _severity_style(issue.get("severity", "low"))
                file_info = f"{issue.get('file', '')}:{issue.get('line', '')}" if issue.get('file') else ""
                lines.append(f"      {sev_color}[{sev_icon}]{RESET} {issue.get('message', '')} {DIM}{file_info}{RESET}")
    else:
        lines.append(f"  {GREEN}No issues found!{RESET}")

    lines.append("")

    # AI Insights
    ai_summary = insights.get("summary", "")
    if ai_summary:
        lines.append(f"  {BOLD}AI Insights:{RESET}")
        for line in ai_summary.strip().split("\n"):
            lines.append(f"    {line}")
        lines.append("")

    # Quick fixes
    quick_fixes = insights.get("quick_fixes", [])
    if quick_fixes:
        lines.append(f"  {BOLD}Quick Fixes:{RESET}")
        for qf in quick_fixes[:5]:  # Show top 5
            effort_colors = {"low": GREEN, "medium": YELLOW, "high": RED}
            effort_color = effort_colors.get(qf.get("effort", "medium"), YELLOW)
            lines.append(f"    {effort_color}[{qf.get('effort', '?').upper()}]{RESET} {qf.get('issue', '')[:50]}... -> {qf.get('fix', '')[:60]}")
        lines.append("")

    lines.append(f"  {DIM}Run with --format html for a beautiful report.{RESET}")
    lines.append(f"  {DIM}Run with --no-ai to skip AI insights (faster).{RESET}")
    lines.append("")

    return "\n".join(lines)


def format_html_report(scorecard: dict, insights: dict, repo_name: str) -> str:
    """Format the results as an interactive HTML report."""
    from codepulse.report import build_html

    return build_html(scorecard, insights, repo_name)

    """Legacy inline formatter retained temporarily for source compatibility."""
    template_path = Path(__file__).parent / "templates" / "scorecard.html"
    if template_path.exists():
        with open(template_path, "r") as f:
            template = f.read()
    else:
        # Fallback inline template
        template = HTML_TEMPLATE

    import base64
    import html
    from datetime import datetime

    # Load logo as base64
    logo_path = Path(__file__).parent.parent / "assets" / "logo.png"
    logo_base64 = ""
    if logo_path.exists():
        with open(logo_path, "rb") as f:
            logo_base64 = base64.b64encode(f.read()).decode("ascii")

    # Prepare data for template
    score = scorecard.get("overall_score", 0)
    grade = scorecard.get("overall_grade", "N/A")

    if score >= 80:
        score_class = "grade-a"
    elif score >= 50:
        score_class = "grade-b"
    elif score >= 30:
        score_class = "grade-c"
    else:
        score_class = "grade-f"

    dims_html = ""
    for cat, data in scorecard.get("dimensions", {}).items():
        cat_score = data.get("score", 0)
        cat_grade = data.get("grade", "N/A")
        pct = cat_score
        dims_html += f"""
        <div class="dimension">
            <div class="dim-header">
                <span class="dim-name">{cat.capitalize()}</span>
                <span class="dim-score">{cat_score:.0f}/100</span>
                <span class="dim-grade">{cat_grade}</span>
            </div>
            <div class="dim-bar"><div class="dim-fill" style="width: {pct}%"></div></div>
        </div>"""

    issues_html = ""
    issues_by_cat = scorecard.get("issues_by_category", {})
    for cat, cat_issues in issues_by_cat.items():
        if not cat_issues:
            continue
        issues_html += f"<h3>{cat.capitalize()}</h3>\n<ul class='issues'>"
        for issue in cat_issues:
            severity = issue.get("severity", "low")
            file_info = f"{issue.get('file', '')}:{issue.get('line', '')}" if issue.get('file') else ""
            # Build evidence from issue details
            evidence_parts = []
            if issue.get('message'):
                evidence_parts.append(f"Message: {html.escape(issue.get('message', ''))}")
            if file_info:
                evidence_parts.append(f"Location: {html.escape(file_info)}")
            if issue.get('category'):
                evidence_parts.append(f"Category: {html.escape(issue.get('category', ''))}")
            evidence_html = "<br>".join(evidence_parts) if evidence_parts else "No additional details."
            issues_html += f"""<li class='issue severity-{severity}'>
                <div class='issue-header'>
                    <span class='sev-badge'>{severity.upper()}</span>
                    <span class='issue-message'>{html.escape(issue.get('message', ''))}</span>
                    <span class='file-info'>{html.escape(file_info)}</span>
                    <button class='evidence-toggle' type='button'>Show evidence</button>
                    <button class='copy-btn' type='button' title='Copy issue'>Copy</button>
                </div>
                <div class='issue-evidence'>{evidence_html}</div>
            </li>"""
        issues_html += "</ul>"

    ai_html = ""
    ai_summary = insights.get("summary", "")
    if ai_summary:
        ai_html = f"<div class='section ai-insights'><h2>AI Insights</h2><div class='ai-content'>{html.escape(ai_summary).replace(chr(10), '<br>')}</div></div>"

    fixes_html = ""
    quick_fixes = insights.get("quick_fixes", [])
    if quick_fixes:
        fixes_html = "<div class='section quick-fixes'><h2>Quick Fixes</h2><ul class='fixes'>"
        for qf in quick_fixes:
            effort = qf.get("effort", "medium")
            fixes_html += f"<li class='effort-{effort}'><span class='effort-badge'>{effort.upper()}</span> <strong>{html.escape(qf.get('issue', ''))}</strong>: {html.escape(qf.get('fix', ''))}</li>"
        fixes_html += "</ul></div>"

    html_output = template.replace("{{ repo_name }}", html.escape(repo_name))
    html_output = html_output.replace("{{ overall_score }}", f"{score:.1f}")
    html_output = html_output.replace("{{ overall_grade }}", grade)
    html_output = html_output.replace("{{ score_class }}", score_class)
    html_output = html_output.replace("{{ score_deg }}", f"{score * 3.6:.1f}deg")
    html_output = html_output.replace("{{ dimensions }}", dims_html)
    html_output = html_output.replace("{{ issues }}", issues_html if issues_html else "<p class='no-issues'>No issues found!</p>")
    html_output = html_output.replace("{{ ai_insights }}", ai_html)
    html_output = html_output.replace("{{ quick_fixes }}", fixes_html)
    html_output = html_output.replace("{{ timestamp }}", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    html_output = html_output.replace("{{ logo_base64 }}", logo_base64)

    return html_output


# Fallback inline HTML template
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CodePulse - Code Health Scorecard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
            --bg: #0d1117; --bg-elevated: #161b22; --border: #30363d;
            --text: #c9d1d9; --text-muted: #8b949e; --accent: #58a6ff;
            --green: #238636; --green-bright: #3fb950; --blue: #1f6feb;
            --yellow: #d29922; --red: #da3633; --purple: #a371f7;
        }
        @media (prefers-color-scheme: light) {
            :root { --bg: #ffffff; --bg-elevated: #f6f8fa; --border: #d0d7de;
                    --text: #24292f; --text-muted: #656d76; --accent: #0969da; }
        }
        body.light { --bg: #ffffff; --bg-elevated: #f6f8fa; --border: #d0d7de;
                     --text: #24292f; --text-muted: #656d76; --accent: #0969da; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: var(--bg); color: var(--text); line-height: 1.6; padding: 2rem; transition: background 0.3s, color 0.3s; }
        .container { max-width: 1000px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; flex-wrap: wrap; gap: 1rem; }
        .logo { display: flex; align-items: center; justify-content: center; }
        .logo-img { width: 180px; height: 45px; }
        .tagline { color: var(--text-muted); }
        .theme-toggle { background: var(--bg-elevated); border: 1px solid var(--border); border-radius: 8px; padding: 0.5rem 1rem; cursor: pointer; font-size: 0.9rem; color: var(--text); transition: all 0.2s; }
        .theme-toggle:hover { background: var(--border); }
        .score-card { background: var(--bg-elevated); border: 1px solid var(--border); border-radius: 16px; padding: 2rem; text-align: center; margin-bottom: 2rem; position: relative; }
        .score-circle { width: 180px; height: 180px; border-radius: 50%; margin: 0 auto 1rem; display: flex; flex-direction: column; justify-content: center; align-items: center; position: relative; animation: pulse 2s ease-in-out infinite; box-shadow: 0 0 30px rgba(0,0,0,0.3); }
        .score-circle.grade-a { background: conic-gradient(var(--green) var(--score-deg), var(--border) 0deg); }
        .score-circle.grade-b { background: conic-gradient(var(--blue) var(--score-deg), var(--border) 0deg); }
        .score-circle.grade-c { background: conic-gradient(var(--yellow) var(--score-deg), var(--border) 0deg); }
        .score-circle.grade-f { background: conic-gradient(var(--red) var(--score-deg), var(--border) 0deg); }
        .score-circle::before { content: ""; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 140px; height: 140px; border-radius: 50%; background: var(--bg); z-index: 1; }
        .score-value { position: relative; z-index: 2; font-size: 3.5rem; font-weight: 700; }
        .score-grade { position: relative; z-index: 2; font-size: 1.5rem; color: var(--text-muted); margin-top: 0.5rem; }
        .score-delta { margin-top: 1rem; font-size: 1.2rem; font-weight: 600; }
        .section { background: var(--bg-elevated); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }
        .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border); }
        .section h2 { color: var(--accent); font-size: 1.3rem; }
        .section h3 { color: var(--accent); font-size: 1.05rem; margin: 1rem 0 0.5rem; padding-bottom: 0.25rem; border-bottom: 1px solid var(--border); }
        .filter-bar { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        .filter-btn { background: transparent; border: 1px solid var(--border); border-radius: 6px; padding: 0.4rem 0.8rem; cursor: pointer; font-size: 0.8rem; color: var(--text); transition: all 0.15s; }
        .filter-btn:hover, .filter-btn.active { background: var(--accent); border-color: var(--accent); color: white; }
        .dimensions { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; }
        .dimension { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; transition: transform 0.15s, box-shadow 0.15s; }
        .dimension:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.3); }
        .dim-header { display: flex; justify-content: space-between; margin-bottom: 0.5rem; }
        .dim-name { font-weight: 600; font-size: 1rem; }
        .dim-score { color: var(--text-muted); font-size: 0.9rem; }
        .dim-grade { font-weight: 700; font-size: 1.1rem; }
        .dim-bar { height: 10px; background: var(--border); border-radius: 5px; overflow: hidden; margin-top: 0.5rem; }
        .dim-fill { height: 100%; background: linear-gradient(90deg, var(--green), var(--green-bright)); border-radius: 5px; transition: width 0.8s cubic-bezier(0.4,0,0.2,1); }
        .issues ul { list-style: none; }
        .issue { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; margin-bottom: 0.5rem; }
        .issue-header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; flex-wrap: wrap; }
        .sev-badge { font-size: 0.65rem; font-weight: 700; padding: 0.2rem 0.5rem; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
        .issue.severity-critical .sev-badge, .issue.severity-high .sev-badge { background: var(--red); color: white; }
        .issue.severity-medium .sev-badge { background: var(--yellow); color: #0d1117; }
        .issue.severity-low .sev-badge { background: var(--blue); color: white; }
        .issue-message { flex: 1; min-width: 200px; font-weight: 500; }
        .file-info { color: var(--text-muted); font-size: 0.8rem; font-family: ui-monospace, SFMono-Regular, monospace; margin-left: auto; }
        .issue-evidence { display: none; padding: 0.75rem; background: var(--bg); border-radius: 6px; margin-top: 0.5rem; font-size: 0.85rem; line-height: 1.7; color: var(--text-muted); border-left: 3px solid var(--accent); }
        .issue-evidence.visible { display: block; animation: fadeIn 0.2s ease; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        .evidence-toggle { background: none; border: none; color: var(--accent); cursor: pointer; font-size: 0.8rem; padding: 0; margin-left: 0.5rem; text-decoration: underline; }
        .evidence-toggle:hover { color: var(--purple); }
        .ai-insights .ai-content { white-space: pre-wrap; line-height: 1.8; background: var(--bg); padding: 1rem; border-radius: 8px; border-left: 3px solid var(--purple); }
        .quick-fixes ul { list-style: none; }
        .fixes li { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; margin-bottom: 0.5rem; }
        .effort-badge { font-size: 0.65rem; font-weight: 700; padding: 0.2rem 0.5rem; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.05em; margin-right: 0.5rem; }
        .fixes .effort-low .effort-badge { background: var(--green); color: white; }
        .fixes .effort-medium .effort-badge { background: var(--yellow); color: #0d1117; }
        .fixes .effort-high .effort-badge { background: var(--red); color: white; }
        .footer { text-align: center; color: var(--text-muted); font-size: 0.85rem; margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--border); }
        .no-issues { text-align: center; color: var(--green); padding: 3rem; font-size: 1.2rem; }
        @keyframes pulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(88, 166, 255, 0.4); } 50% { box-shadow: 0 0 0 16px rgba(88, 166, 255, 0); } }
        .score-circle.grade-a { animation-name: pulse-green; }
        .score-circle.grade-b { animation-name: pulse-blue; }
        .score-circle.grade-c { animation-name: pulse-yellow; }
        .score-circle.grade-f { animation-name: pulse-red; }
        @keyframes pulse-green { 0%, 100% { box-shadow: 0 0 0 0 var(--green-bright); } 50% { box-shadow: 0 0 0 16px transparent; } }
        @keyframes pulse-blue { 0%, 100% { box-shadow: 0 0 0 0 var(--blue); } 50% { box-shadow: 0 0 0 16px transparent; } }
        @keyframes pulse-yellow { 0%, 100% { box-shadow: 0 0 0 0 var(--yellow); } 50% { box-shadow: 0 0 0 16px transparent; } }
        @keyframes pulse-red { 0%, 100% { box-shadow: 0 0 0 0 var(--red); } 50% { box-shadow: 0 0 0 16px transparent; } }
        .copy-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.75rem; padding: 0.2rem 0.5rem; border-radius: 4px; opacity: 0; transition: opacity 0.2s; }
        .issue:hover .copy-btn { opacity: 1; }
        .copy-btn:hover { color: var(--accent); background: var(--bg-elevated); }
        .keyboard-hint { position: fixed; bottom: 1rem; right: 1rem; background: var(--bg-elevated); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem 1rem; font-size: 0.75rem; color: var(--text-muted); z-index: 100; }
        .keyboard-hint kbd { background: var(--border); padding: 0.1rem 0.4rem; border-radius: 4px; margin: 0 0.2rem; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <div class="logo">
                    <img src="data:image/png;base64,{{ logo_base64 }}" alt="CodePulse" class="logo-img" width="180" height="45"/>
                </div>
                <div class="tagline">Code Health Scorecard for {{ repo_name }}</div>
            </div>
            <button class="theme-toggle" id="themeToggle" title="Toggle theme">[T]</button>
        </div>
        <div class="score-card">
            <div class="score-circle {{ score_class }}" style="--score-deg: {{ score_deg }};">
                <span class="score-value">{{ overall_score }}</span>
                <span class="score-grade">Grade {{ overall_grade }}</span>
            </div>
        </div>
        <div class="section">
            <div class="section-header">
                <h2>Category Breakdown</h2>
            </div>
            <div class="dimensions">{{ dimensions }}</div>
        </div>
        <div class="section">
            <div class="section-header">
                <h2>Issues Found</h2>
                <div class="filter-bar">
                    <button class="filter-btn active" data-filter="all">All</button>
                    <button class="filter-btn" data-filter="critical">Critical</button>
                    <button class="filter-btn" data-filter="high">High</button>
                    <button class="filter-btn" data-filter="medium">Medium</button>
                    <button class="filter-btn" data-filter="low">Low</button>
                </div>
            </div>
            {{ issues }}
        </div>
        {{ ai_insights }}
        {{ quick_fixes }}
        <div class="footer">Generated by CodePulse at {{ timestamp }}</div>
    </div>
    <div class="keyboard-hint">
        <kbd>F</kbd> Filter  <kbd>E</kbd> Expand all  <kbd>C</kbd> Copy issue  <kbd>T</kbd> Theme
    </div>
    <script>
        // Theme toggle
        const themeBtn = document.getElementById('themeToggle');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const storedTheme = localStorage.getItem('theme');
        if (storedTheme === 'light' || (!storedTheme && !prefersDark)) document.body.classList.add('light');
themeBtn.textContent = document.body.classList.contains('light') ? '[Sun]' : '[Moon]';
        themeBtn.onclick = () => {
            document.body.classList.toggle('light');
            localStorage.setItem('theme', document.body.classList.contains('light') ? 'light' : 'dark');
themeBtn.textContent = document.body.classList.contains('light') ? '[Sun]' : '[Moon]';
        };

        // Issue filtering
        const filterBtns = document.querySelectorAll('.filter-btn');
        const issues = document.querySelectorAll('.issue');
        filterBtns.forEach(btn => {
            btn.onclick = () => {
                filterBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const filter = btn.dataset.filter;
                issues.forEach(issue => {
                    if (filter === 'all' || issue.classList.contains('severity-' + filter)) {
                        issue.style.display = '';
                    } else {
                        issue.style.display = 'none';
                    }
                });
            };
        });

        // Expand/collapse evidence
        document.querySelectorAll('.evidence-toggle').forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation();
                const evidence = btn.closest('.issue').querySelector('.issue-evidence');
                evidence.classList.toggle('visible');
                btn.textContent = evidence.classList.contains('visible') ? 'Hide evidence' : 'Show evidence';
            };
        });

        // Click issue to expand
        document.querySelectorAll('.issue').forEach(issue => {
            issue.onclick = (e) => {
                if (e.target.closest('.evidence-toggle') || e.target.closest('.copy-btn')) return;
                const evidence = issue.querySelector('.issue-evidence');
                if (evidence) {
                    evidence.classList.toggle('visible');
                }
            };
        });

        // Copy issue to clipboard
        document.querySelectorAll('.copy-btn').forEach(btn => {
            btn.onclick = async (e) => {
                e.stopPropagation();
                const issue = btn.closest('.issue');
                const text = issue.querySelector('.issue-message').textContent + ' -- ' + issue.querySelector('.file-info').textContent;
                await navigator.clipboard.writeText(text);
                btn.textContent = 'Copied!';
                setTimeout(() => btn.textContent = 'Copy', 1500);
            };
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
            if (e.key === 'f' || e.key === 'F') document.querySelector('.filter-btn[data-filter="all"]')?.focus();
            if (e.key === 'e' || e.key === 'E') document.querySelectorAll('.issue-evidence').forEach(el => el.classList.add('visible'));
            if (e.key === 'c' || e.key === 'C') document.querySelector('.copy-btn')?.click();
            if (e.key === 't' || e.key === 'T') themeBtn.click();
        });

        // Expand all on 'E'
        document.addEventListener('keydown', (e) => {
            if ((e.key === 'e' || e.key === 'E') && e.ctrlKey) {
                e.preventDefault();
                document.querySelectorAll('.issue-evidence').forEach(el => el.classList.add('visible'));
            }
        });
    </script>
</body>
</html>"""


def install_hook(repo_path: Path) -> int:
    """Install pre-commit hook."""
    if not (repo_path / ".git").exists():
        print(f"  Error: Not a Git repository: {repo_path}")
        return 1
    hook_path = repo_path / ".git" / "hooks" / "pre-commit"
    hook_content = """#!/bin/sh
# CodePulse pre-commit hook
echo "Running CodePulse pre-commit scan..."
python -m codepulse scan --no-ai --format text
if [ $? -ne 0 ]; then
    echo "CodePulse scan failed. Commit aborted."
    exit 1
fi
"""
    try:
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        hook_path.write_text(hook_content)
        hook_path.chmod(0o755)
        print(f"  Pre-commit hook installed at {hook_path}")
        return 0
    except OSError as e:
        print(f"  Error installing hook: {e}")
        return 1


def install_hook_entrypoint() -> None:
    """Install the pre-commit hook in the current repository."""
    raise SystemExit(install_hook(Path.cwd()))


def run_scan(args, repo_path: Path, repo_name: str) -> int:
    """Run the scan command."""
    print(f"  Analyzing: {repo_path}")
    print()

    # Run analyzers
    results = run_analyzers(repo_path)

    # Compute scorecard
    show_progress("Computing scorecard")
    sc, scorecard = compute_scorecard(results)

    # Generate AI insights
    if not args.no_ai:
        show_progress("Generating AI insights")
    else:
        print("  [*] Skipping AI insights (--no-ai)")
    insights = generate_ai_insights(sc, scorecard["issues"], repo_name, args.no_ai)

    print()

    # Output
    if args.json:
        output = json.dumps({"scorecard": scorecard, "insights": insights}, indent=2, default=str)
        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"  JSON report saved to {args.output}")
        else:
            print(output)
    elif args.format == "html":
        output = format_html_report(scorecard, insights, repo_name)
        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"  HTML report saved to {args.output}")
            if args.auto_open:
                import webbrowser
                webbrowser.open(f"file://{Path(args.output).resolve()}")
        else:
            print(output)
    else:
        output = format_text_report(scorecard, insights)
        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"  Text report saved to {args.output}")
        else:
            print(output)

    print()
    return 0


def main() -> int:
    """Main CLI entry point."""
    print(BANNER)

    args = parse_args()

    # Handle diff command
    if args.command == "diff":
        from .diff import run_diff
        return run_diff(args.ref1, args.ref2, Path(args.repo_path))

    # Handle install-hook command
    if args.command == "install-hook":
        return install_hook(Path(args.repo_path))

    # Default: scan command
    repo_path = validate_repo_path(args.repo_path)
    repo_name = repo_path.name or "repository"

    return run_scan(args, repo_path, repo_name)


if __name__ == "__main__":
    sys.exit(main())
