#!/usr/bin/env python3
"""Install the same Papis Logger skill into Codex, Claude Code, or both."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import tempfile
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("codex", "claude", "both"))
    parser.add_argument("--project", type=Path, help="Install in this project's skill directories")
    parser.add_argument("--skills-dir", type=Path, help="Custom skills parent directory (one target only)")
    parser.add_argument("--replace", action="store_true", help="Back up and replace an existing installation")
    args = parser.parse_args()
    if args.skills_dir and (args.project or args.target == "both"):
        parser.error("--skills-dir cannot be combined with --project or target 'both'")
    root = args.project.expanduser().resolve() if args.project else Path.home()
    if not root.is_dir():
        parser.error(f"Project directory does not exist: {root}")
    source = Path(__file__).resolve().parent / "papis-logger"
    targets = ("codex", "claude") if args.target == "both" else (args.target,)
    destinations = []
    for target in targets:
        parent = (args.skills_dir.expanduser().resolve() if args.skills_dir else
                  root / (".agents" if target == "codex" else ".claude") / "skills")
        destination = parent / source.name
        resolved = destination.resolve()
        if resolved.is_relative_to(source) or source.is_relative_to(resolved):
            parser.error("Source and destination directories must not overlap")
        if os.path.lexists(destination) and not args.replace:
            parser.error(f"Already installed: {destination}. Use --replace to back it up and update.")
        destinations.append(destination)
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".papis-logger-install-", dir=destination.parent) as stage:
            staged = Path(stage) / source.name
            shutil.copytree(source, staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            backup = None
            if os.path.lexists(destination):
                # Outside the discovery directory so the backup isn't loaded as a second skill.
                backup_root = destination.parent.parent / "skill-backups"
                backup_root.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                backup = backup_root / f"papis-logger-{stamp}-{uuid.uuid4().hex[:8]}"
                destination.rename(backup)
            try:
                staged.rename(destination)
            except OSError:
                if backup is not None:
                    backup.rename(destination)
                raise
        print(f"Installed: {destination}")
        if backup is not None:
            print(f"Previous version: {backup}")


if __name__ == "__main__":
    main()
