import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

GAMES = ("SF3", "SFA")
MANIFEST = "manifest.json"


def log(msg):
    print(msg, flush=True)


def signature(dest: Path) -> str:
    """Fingerprint of frames + gif + meta; stored inside the zip."""
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
    return hashlib.sha256(json.dumps(
        {"frames": items, "gif": gif_info, "meta": meta_hash},
        sort_keys=True).encode()).hexdigest()


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
            {"signature": signature(dest), "effect": dest.name}, indent=2))
    os.replace(tmp, zp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--dirs", default=None,
                    help="file with effect dirs relative to repo root, one per line")
    ap.add_argument("--no-commit", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()

    if args.dirs:
        candidates = []
        for line in Path(args.dirs).read_text().splitlines():
            line = line.strip().replace("\\", "/")
            if line:
                p = repo / line
                if p.is_dir() and p.parent.name in GAMES:
                    candidates.append(p)
    else:
        candidates = []
        for game in GAMES:
            root = repo / game
            if root.is_dir():
                candidates += [p for p in root.iterdir() if p.is_dir()]

    changed = [d for d in candidates if (d / "frames").is_dir()
               and needs_zip(d)]
    log(f"{len(changed)} effect(s) need zipping")

    paths = []
    for i, folder in enumerate(changed, 1):
        make_zip(folder)
        paths.append((folder / "frames.zip").relative_to(repo).as_posix())
        if i % 100 == 0:
            log(f"  zipped {i}/{len(changed)}")

    Path("zip_paths.txt").write_text("\n".join(paths), encoding="utf-8")
    log(f"wrote zip_paths.txt ({len(paths)} paths)")


if __name__ == "__main__":
    main()
