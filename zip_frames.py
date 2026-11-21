import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

HERE = Path(__file__).resolve().parent
GAMES = ("SF3", "SFA")
MANIFEST = "manifest.json"
COMMIT_PREFIX = "chore: update frame archives"


def log(msg):
    print(msg, flush=True)


def signature(dest: Path) -> str:
    frames = dest / "frames"
    items = []
    if frames.is_dir():
        for f in sorted(frames.iterdir()):
            if f.is_file():
                items.append([f.name, f.stat().st_size])
    gif = dest / f"{dest.name}.gif"
    gif_info = [gif.name, gif.stat().st_size] if gif.is_file() else None
    meta = dest / "meta.json"
    meta_hash = (hashlib.sha256(meta.read_bytes()).hexdigest()
                 if meta.is_file() else "")
    raw = json.dumps({"frames": items, "gif": gif_info, "meta": meta_hash},
                     sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def needs_zip(dest: Path) -> bool:
    zp = dest / "frames.zip"
    if not zp.is_file():
        return True
    try:
        with ZipFile(zp) as z:
            old = json.loads(z.read(MANIFEST).decode("utf-8"))
        return old.get("signature") != signature(dest)
    except Exception:
        return True


def make_zip(dest: Path):
    zp = dest / "frames.zip"
    tmp = dest / "frames.zip.tmp"
    with ZipFile(tmp, "w", ZIP_DEFLATED, compresslevel=6) as z:
        frames = dest / "frames"
        if frames.is_dir():
            for f in sorted(frames.iterdir()):
                if f.is_file():
                    z.write(f, f"frames/{f.name}")
        z.writestr(MANIFEST, json.dumps(
            {"signature": signature(dest), "effect": dest.name},
            indent=2))
    os.replace(tmp, zp)


def git(repo: Path, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(HERE if (HERE / "SF3").is_dir()
                                          else HERE / "vfx_repo"))
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--chunk", type=int, default=50,
                    help="effects per commit")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    changed = []
    for game in GAMES:
        root = repo / game
        if not root.is_dir():
            continue
        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            if not (folder / "frames").is_dir():
                continue
            if needs_zip(folder):
                changed.append(folder)

    print(f"{len(changed)} effect(s) need zipping", flush=True)
    if not changed:
        return

    for i, folder in enumerate(changed, 1):
        make_zip(folder)
        if i % 100 == 0:
            print(f"  zipped {i}/{len(changed)}", flush=True)

    if args.no_commit:
        return

    for start in range(0, len(changed), args.chunk):
        batch = changed[start:start + args.chunk]
        git(repo, "add", "--force", "--",
            *[str(p.relative_to(repo).as_posix()) + "/frames.zip"
              for p in batch])
        c = git(repo, "commit", "-m",
                f"{COMMIT_PREFIX} ({len(batch)} effects)")
        if c.returncode != 0:
            if "nothing to commit" in (c.stdout + c.stderr).lower():
                continue
            log(f"commit failed: {c.stderr[:300]}")
            return
        for attempt in range(1, 5):
            r = git(repo, "push", "origin", "HEAD:refs/heads/main")
            if r.returncode == 0:
                break
            git(repo, "pull", "--rebase", "--autostash", "origin", "main")
            time.sleep(3 * attempt)
        log(f"pushed {len(batch)} archives "
            f"({min(start + args.chunk, len(changed))}/{len(changed)})")


if __name__ == "__main__":
    main()
