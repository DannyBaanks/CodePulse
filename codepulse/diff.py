"""Git diff comparison for CodePulse — compare scores between commits."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .cli import compute_scorecard, run_analyzers
from .scorer import Scorecard


def get_git_root(path: Path) -> Path:
    """Find the git repository root."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path, capture_output=True, text=True, check=True
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return path


def get_commit_hash(ref: str, repo_path: Path) -> str:
    """Resolve a git reference to a full commit hash."""
    result = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=repo_path, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()[:8]


def checkout_commit(commit: str, repo_path: Path, workdir: Path) -> None:
    """Checkout a commit to a temporary work directory."""
    # Use git worktree for clean isolation
    subprocess.run(
        ["git", "-c", f"core.hooksPath={workdir / '.codepulse-no-hooks'}", "worktree", "add", "--force", str(workdir), commit],
        cwd=repo_path, capture_output=True, check=True
    )


def cleanup_worktree(workdir: Path, repo_path: Path) -> None:
    """Remove the temporary worktree."""
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(workdir)],
            cwd=repo_path, capture_output=True, check=False
        )
    except OSError:
        return
    # Fallback cleanup
    if workdir.exists():
        shutil.rmtree(workdir, ignore_errors=True)


def analyze_at_commit(commit: str, repo_path: Path) -> Scorecard:
    """Run full analysis at a specific commit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir) / "scan"
        checkout_commit(commit, repo_path, workdir)
        try:
            results = run_analyzers(workdir)
            sc, _ = compute_scorecard(results)
            return sc
        finally:
            cleanup_worktree(workdir, repo_path)


def format_diff(before: Scorecard, after: Scorecard) -> str:
    """Format a human-readable diff between two scorecards."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    lines = []
    lines.append("")
    lines.append(f"{BOLD}{CYAN}{'=' * 60}{RESET}")
    lines.append(f"{BOLD}{CYAN}  CODEPULSE - Score Diff{RESET}")
    lines.append(f"{BOLD}{CYAN}{'=' * 60}{RESET}")
    lines.append("")

    # Overall
    overall_delta = after.overall_score - before.overall_score
    delta_color = GREEN if overall_delta > 0 else (RED if overall_delta < 0 else YELLOW)
    lines.append(f"  {BOLD}Overall:{RESET}  {before.overall_score:.1f} -> {after.overall_score:.1f}  {delta_color}{BOLD}{overall_delta:+.1f}{RESET}")
    lines.append(f"  {BOLD}Grade:{RESET}     {before.overall_grade} -> {after.overall_grade}")
    lines.append("")

    # Per dimension
    lines.append(f"  {BOLD}Dimensions:{RESET}")
    all_dims = set(before.dimensions.keys()) | set(after.dimensions.keys())
    for dim in sorted(all_dims):
        b = before.dimensions.get(dim)
        a = after.dimensions.get(dim)
        b_score = b.score if b else 0
        a_score = a.score if a else 0
        delta = a_score - b_score
        delta_color = GREEN if delta > 0 else (RED if delta < 0 else YELLOW)
        bar_len = int(a_score / 5)
        bar = "#" * bar_len + "-" * (20 - bar_len)
        grade = a.grade if a else "?"
        lines.append(f"    {dim.capitalize():15} {bar} {delta_color}{a_score:.0f}{RESET} ({grade})  {delta_color}{delta:+.0f}{RESET}")

    lines.append("")

    # Summary
    if overall_delta > 0:
        lines.append(f"  {GREEN}[+] Score improved by {overall_delta:.1f} points!{RESET}")
    elif overall_delta < 0:
        lines.append(f"  {RED}[-] Score decreased by {abs(overall_delta):.1f} points.{RESET}")
    else:
        lines.append(f"  {YELLOW}[~] Score unchanged.{RESET}")

    lines.append("")
    return "\n".join(lines)


def run_diff(ref1: str, ref2: str, repo_path: Path | None = None) -> int:
    """Main entry point for diff command."""
    if repo_path is None:
        repo_path = Path.cwd()

    repo_path = get_git_root(repo_path)

    print("  Resolving commits...")
    c1 = get_commit_hash(ref1, repo_path)
    c2 = get_commit_hash(ref2, repo_path)

    print(f"  Analyzing {c1}...")
    before = analyze_at_commit(c1, repo_path)

    print(f"  Analyzing {c2}...")
    after = analyze_at_commit(c2, repo_path)

    print(format_diff(before, after))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m codepulse.diff <commit1> <commit2> [repo_path]")
        sys.exit(1)

    ref1, ref2 = sys.argv[1], sys.argv[2]
    repo = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    sys.exit(run_diff(ref1, ref2, repo))
