#!/usr/bin/env python3
"""Run frontend checks/builds, with an isolated scratch checkout on macOS Documents.

esbuild enumerates ancestor directories. On macOS an iCloud-backed Documents
folder may stall that traversal. Source remains in the repository; only execution
and dependencies are copied to a temporary directory. Built assets are copied back.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run():
    command = sys.argv[1] if len(sys.argv) == 2 else "check"
    if command not in {"test", "check", "build"}:
        raise SystemExit("Usage: python3 scripts/frontend.py [test|check|build]")
    env = os.environ.copy()
    bundled = ROOT / ".tools" / "node" / "bin"
    if bundled.is_dir():
        env["PATH"] = str(bundled) + os.pathsep + env.get("PATH", "")
    npm = shutil.which("npm", path=env.get("PATH"))
    if not npm:
        raise SystemExit("Node.js 22.14+ and npm are required. Install Node.js, then run npm ci in frontend/.")
    source = ROOT / "frontend"
    if not (source / "node_modules").is_dir():
        raise SystemExit("Run npm ci in frontend/ first.")
    use_scratch = sys.platform == "darwin" and "Documents" in ROOT.parts
    if not use_scratch:
        return subprocess.call([npm, "run", command], cwd=source, env=env)
    with tempfile.TemporaryDirectory(prefix="signal-ui-") as directory:
        target = Path(directory)
        print("Using temporary build workspace for macOS Documents; source stays in the repository.", flush=True)
        def ignore(directory, names):
            if Path(directory).name == "node_modules":
                return [n for n in names if n in {".vite", ".vite-temp"}]
            if Path(directory) == source:
                return [n for n in names if n == "dist" or n.endswith(".tsbuildinfo")]
            return []
        shutil.copytree(source, target / "frontend", symlinks=True, ignore=ignore)
        fixture_dir = target / "backend" / "app"
        fixture_dir.mkdir(parents=True)
        for fixture in (ROOT / "backend/app").glob("demo_*.json"):
            shutil.copy2(fixture, fixture_dir)
        result = subprocess.call([npm, "run", command], cwd=target / "frontend", env=env)
        if result == 0 and command in {"build", "check"}:
            shutil.copytree(target / "frontend/dist", source / "dist", dirs_exist_ok=True)
        return result


if __name__ == "__main__":
    sys.exit(run())
