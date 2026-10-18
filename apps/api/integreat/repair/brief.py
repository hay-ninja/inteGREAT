"""Repair brief construction + git snapshot checks (D-025).

The brief is what we actually send to Devin Cloud. It is persisted verbatim on the RepairJob for
audit, names the exact base commit, marks every claim with its trust label, forbids relaxing the
engineer-confirmed expectation, and requires a reviewable diff/PR — never a patch applied here.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from ..models import (
    Expectation,
    Hypothesis,
    Incident,
    Project,
    RepoSnapshot,
    TestRun,
)

_GIT_TIMEOUT = 10
_REMOTE = re.compile(r"(?:github\.com[:/])([\w.-]+/[\w.-]+?)(?:\.git)?$")


def _git(repo_root: Path, *args: str) -> str | None:
    """Fixed-argument git call — no shell, short timeout, never user-derived args."""
    try:
        r = subprocess.run(["git", "-C", str(repo_root), *args],  # noqa: S603
                           capture_output=True, text=True, timeout=_GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = r.stdout.strip()
    return out if r.returncode == 0 and out else None


def repo_ref_from_remote(url: str | None) -> str | None:
    if not url:
        return None
    m = _REMOTE.search(url.strip())
    return m.group(1) if m else None


def repo_snapshot(repo_root: str) -> RepoSnapshot:
    root = Path(repo_root)
    toplevel = _git(root, "rev-parse", "--show-toplevel")
    head = _git(root, "rev-parse", "HEAD")
    remote = _git(root, "remote", "get-url", "origin")
    porcelain = _git(root, "status", "--porcelain")
    dirty = [ln[3:] for ln in (porcelain or "").splitlines() if ln.strip()] if porcelain is not None else []
    rel = None
    if toplevel:
        try:
            rp = os.path.relpath(root, Path(toplevel))
            rel = None if rp == "." else rp.replace("\\", "/")
        except ValueError:
            rel = None
    return RepoSnapshot(repo_root=str(root), git_toplevel=toplevel, remote_url=remote,
                        repo_ref=repo_ref_from_remote(remote), base_revision=head,
                        relative_path=rel, dirty_files=dirty[:50])


def build_brief(project: Project, inc: Incident, exp: Expectation, run: TestRun,
                hyps: list[Hypothesis], evidence_lines: list[str], snap: RepoSnapshot,
                repo_ref: str) -> str:
    """The exact prompt sent to Devin. Under 6k chars by construction."""
    repo_line = repo_ref or snap.remote_url or "(no accessible remote — see constraints)"
    facts = []
    if run.result:
        facts = [f"  - {f.label}: {f.value}" + (f" — {f.note}" if f.note else "") for f in run.result.facts]
    hyp_lines = [f"  - [{h.status.value}] {h.title}: {h.explanation[:300]}" for h in hyps[:4]]
    subdir = f"\n- The firmware project lives in subdirectory `{snap.relative_path}` of that repo." \
        if snap.relative_path else ""
    dirty = (f"\n- The engineer's checkout has {len(snap.dirty_files)} uncommitted file(s) that are NOT "
             "visible to you; the base commit above is the source of truth.") if snap.dirty_files else ""
    return f"""You are preparing a MINIMAL software fix for review by an embedded engineer, inside your
isolated Devin Cloud sandbox on a new branch. You must not deploy, merge, flash firmware, reboot
devices, or actuate hardware — none of those are possible or permitted from inteGREAT.

## Repository
- Remote repo: {repo_line}
- Base commit to branch from: {snap.base_revision or "(unknown — the project may not be committed; report this)"}{subdir}{dirty}
- Project name: {project.name}

## Confirmed expectation (do NOT relax these thresholds)
- Sending `{exp.trigger.value}` makes {exp.component_id} reach {exp.target:g}° ± {exp.tolerance:g}°
  within {exp.deadline_ms} ms (camera-measured; engineer-confirmed).

## What was observed (trust labels preserved)
- Outcome: {(run.result.outcome.value if run.result else 'unknown')} — {(run.result.reason if run.result else '')}
{chr(10).join(facts) or '  - (no fact list recorded)'}
- Evidence and findings (ids are inteGREAT evidence references; each has a trust label):
{chr(10).join('  - ' + ln for ln in evidence_lines[:24]) or '  - (none)'}

## Ranked hypotheses from deterministic rules
{chr(10).join(hyp_lines) or '  - (none)'}

## What to do
1. Inspect the repository; consult the official ESP32 Arduino core and Servo library documentation
   for pin/timer constraints relevant to the failure.
2. Reproduce the software fault from the evidence (e.g. a pin constant that disagrees with wiring).
3. Evaluate at least one alternative explanation and say why it does or does not fit the evidence.
4. Make the smallest correct fix on a new branch. Do not weaken the test/expectation thresholds.
5. Run the most relevant regression checks you can (compile for the ESP32 target if the toolchain is
   available, else unit/static checks) and report exactly what ran and what passed.
6. Open a PR or return a complete diff plus your structured output (summary, tests_run,
   tests_passed, risks, branch). List unresolved risks explicitly — especially anything that still
   needs physical-hardware verification, which you cannot perform.
Do not spawn additional paid sessions, do not call inteGREAT's repair endpoint, do not exfiltrate
or modify anything outside the task repo."""


REPAIR_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "tests_run": {"type": "array", "items": {"type": "string"}},
        "tests_passed": {"type": "boolean"},
        "risks": {"type": "array", "items": {"type": "string"}},
        "branch": {"type": "string"},
        "pr_url": {"type": "string"},
    },
    "required": ["summary", "tests_run", "tests_passed", "risks", "branch", "pr_url"],
    "additionalProperties": False,
}
