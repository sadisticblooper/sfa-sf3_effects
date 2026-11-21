from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
DEFAULT_REPO = HERE / "vfx_repo"
GAMES = ("SF3", "SFA")


def log(msg):
    print(msg, flush=True)


class Lock:
    def __init__(self, repo: Path, timeout=600.0):
        self.lock_file = repo.parent / (repo.name + ".lock")
        self.timeout = timeout
        self.acquired = False

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                fd = os.open(str(self.lock_file),
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                self.acquired = True
                return self
            except FileExistsError:
                try:
                    if time.time() - self.lock_file.stat().st_mtime > 900:
                        self.lock_file.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    return self
                time.sleep(0.5)

    def __exit__(self, *exc):
        if self.acquired:
            try:
                self.lock_file.unlink(missing_ok=True)
            except OSError:
                pass
        return False


def clear_stale_git_locks(repo: Path):
    for name in ("index.lock", "HEAD.lock"):
        lock = repo / ".git" / name
        try:
            if lock.is_file() and time.time() - lock.stat().st_mtime > 120:
                lock.unlink(missing_ok=True)
        except OSError:
            pass


def git(repo: Path, *args, retries=3):
    last = None
    for attempt in range(max(1, retries)):
        clear_stale_git_locks(repo)
        last = subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True)
        if last.returncode == 0:
            return last
        err = ((last.stderr or "") + (last.stdout or "")).lower()
        if "lock" not in err:
            break
        time.sleep(1 + attempt)
    return last


def github_base(repo: Path) -> str:
    r = git(repo, "remote", "get-url", "origin")
    url = (r.stdout.strip() if r is not None and r.returncode == 0 else "")
    if not url:
        return ""
    if url.startswith("git@"):
        return "https://github.com/" + re.sub(
            r"\.git$", "", url.split(":", 1)[1])
    parts = urlsplit(url)
    netloc = parts.hostname or ""
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme or "https", netloc,
                       re.sub(r"\.git$", "", parts.path), "", ""))


def build_text(repo: Path, base: str) -> str:
    lines = []
    for game in GAMES:
        root = repo / game
        if not root.is_dir():
            continue
        for folder in sorted(p.name for p in root.iterdir() if p.is_dir()):
            lines.append(f"{folder} | {base}/tree/main/{game}/{folder}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(DEFAULT_REPO))
    ap.add_argument("--no-commit", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / ".git").is_dir():
        log(f"ERROR: not a git repo: {repo}")
        return 1

    with Lock(repo):
        if not args.no_commit:
            git(repo, "fetch", "origin", "main")
            git(repo, "pull", "--rebase", "--autostash", "origin", "main")

        base = github_base(repo)
        text = build_text(repo, base)
        map_path = repo / "map.txt"
        map_path.write_text(text, encoding="utf-8")
        log(f"wrote map.txt: {len(text.splitlines())} lines")

        if args.no_commit:
            return 0

        git(repo, "add", "--", "map.txt")
        if not git(repo, "diff", "--cached", "--name-only").stdout.strip():
            log("map.txt unchanged")
            return 0
        c = git(repo, "commit", "-m", "docs: update map.txt")
        if c is None or c.returncode != 0:
            log(f"ERROR: commit failed: {getattr(c, 'stderr', '')[:300]}")
            return 1

        for attempt in range(1, 5):
            r = git(repo, "push", "origin", "HEAD:refs/heads/main")
            if r is not None and r.returncode == 0:
                log("pushed map.txt")
                return 0
            git(repo, "pull", "--rebase", "--autostash", "origin", "main")
            time.sleep(3 * attempt)
        log("ERROR: push failed after 4 attempts")
        return 1


if __name__ == "__main__":
    sys.exit(main())
