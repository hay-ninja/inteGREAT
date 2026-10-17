"""Safe repository scanning (PRD FR-01). Reads text only; never executes imported code."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SOURCE_EXTS = {".ino", ".cpp", ".c", ".h", ".hpp"}
CONFIG_NAMES = {"platformio.ini", "library.properties", "sketch.yaml"}
SKIP_DIRS = {".git", ".pio", ".vscode", "build", "node_modules", ".venv", "__pycache__", "dist", "out"}
SECRET_NAME = re.compile(r"(^\.env|secret|credential|\.pem$|\.key$|id_rsa)", re.I)

MAX_FILES = 2000
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024


class RepoError(ValueError):
    pass


@dataclass
class RepoFile:
    rel: str  # forward-slash, repo-relative
    text: str


@dataclass
class RepoScan:
    root: Path
    files: list[RepoFile] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (rel, reason)


def resolve_inside(root: Path, rel: str) -> Path:
    """Resolve a repo-relative path and refuse anything outside root (traversal, symlink escape)."""
    root = root.resolve()
    if not rel or Path(rel).is_absolute() or re.match(r"^[a-zA-Z]:", rel):
        raise RepoError(f"path must be repo-relative: {rel!r}")
    candidate = (root / rel).resolve()
    if not candidate.is_relative_to(root):
        raise RepoError(f"path escapes repository: {rel!r}")
    return candidate


def scan_repository(repo_path: str | Path) -> RepoScan:
    root = Path(repo_path).expanduser()
    if not root.is_dir():
        raise RepoError(f"repository path is not a directory: {repo_path}")
    root = root.resolve()
    scan = RepoScan(root=root)
    total = 0

    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            scan.skipped.append((rel, "symlink"))
            continue
        if not path.is_file():
            continue
        if SECRET_NAME.search(path.name):
            scan.skipped.append((rel, "possible secret"))
            continue
        if path.suffix.lower() not in SOURCE_EXTS and path.name not in CONFIG_NAMES:
            continue
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            scan.skipped.append((rel, f"too large ({size} bytes)"))
            continue
        total += size
        if total > MAX_TOTAL_BYTES or len(scan.files) >= MAX_FILES:
            raise RepoError("repository exceeds import size limits")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            scan.skipped.append((rel, "not utf-8 text"))
            continue
        scan.files.append(RepoFile(rel=rel, text=text))

    if not any(f.rel.endswith((".ino", ".cpp", ".c")) for f in scan.files):
        raise RepoError("no Arduino/C/C++ source files found")
    return scan
