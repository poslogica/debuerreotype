#!/usr/bin/env python3
"""
Build SonicSort's own Debian slim rootfs with this fork's debuerreotype.

Produces sonicsort/rootfs/<suite>-slim.tar.xz (plus a .meta.json recording the
snapshot timestamp and sha256), which sonicsort/Dockerfile wraps as
`FROM scratch` -> sonicsort-debian:local. That's the same way the official
debian:<suite>-slim image is made from debuerreotype's output, but built
here, from a pinned snapshot.debian.org timestamp we choose.

    python sonicsort/build_rootfs.py                      # trixie, start of this ISO week
    python sonicsort/build_rootfs.py --timestamp 2026-10-12T00:00:00Z
    python sonicsort/build_rootfs.py --force              # rebuild even if up to date
    python sonicsort/build_rootfs.py --arch amd64         # a foreign arch, emulated

With --arch the output is <suite>-slim-<arch>.tar.xz, so a foreign-arch rootfs
(e.g. amd64 on an Apple Silicon host, for images that must run as amd64) sits
beside the native one instead of replacing it; build it into an image with
`docker build --platform linux/<arch> --build-arg ROOTFS_ARCH=<arch> ...`.

Steps:
  1. docker build this repo's Dockerfile -> the debuerreotype tool image
  2. docker run examples/debian.sh <out> <suite> <timestamp> in it, with the
     capabilities debootstrap needs (mount/unshare; mirrors ./docker-run.sh)
  3. keep <out>/<serial>/<arch>/<suite>/slim/rootfs.tar.xz

The default timestamp is Monday 00:00:00Z of the current ISO week, matching
SonicSort's weekly OS_PATCH_WEEK cadence. Since the rootfs for a given
timestamp is reproducible, the (slow) bootstrap is skipped when
sonicsort/rootfs already holds this suite at this timestamp. To pull in a
security fix mid-week, pass a newer --timestamp.

Patching: package versions come from the snapshot timestamp. To change what's
in the image (packages, minimization, sources), change examples/debian.sh or
scripts/ on this sonicsort/* branch. To ship a patched build of one package,
build that .deb and install it in sonicsort/Dockerfile.

Requires Docker. Runs on Windows/macOS/Linux: docker is invoked directly with
argument lists, no shell.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FORK_ROOT = Path(__file__).resolve().parent.parent
SONICSORT_DIR = FORK_ROOT / "sonicsort"
ROOTFS_DIR = SONICSORT_DIR / "rootfs"


def week_start_timestamp(now: dt.datetime | None = None) -> str:
    """Monday 00:00:00Z of the ISO week containing `now` (UTC), e.g. 2026-10-12T00:00:00Z."""
    now = now or dt.datetime.now(dt.timezone.utc)
    monday = (now - dt.timedelta(days=now.weekday())).date()
    return f"{monday.isoformat()}T00:00:00Z"


def tool_image_tag() -> str:
    """debuerreotype tool image tag, versioned like upstream's .docker-image.sh."""
    version = (FORK_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    return f"sonicsort-debuerreotype:{version}"


def run_args(
    image: str, output_dir: Path, suite: str, timestamp: str, arch: str | None
) -> list[str]:
    """`docker run` argv for examples/debian.sh -- the same isolation flags as ./docker-run.sh."""
    args = [
        "docker",
        "run",
        "--rm",
        "--init",
        "--hostname",
        "debuerreotype",
        # debootstrap needs mount/unshare; no extended attributes in the output
        "--cap-add",
        "SYS_ADMIN",
        "--cap-drop",
        "SETFCAP",
        "--security-opt",
        "apparmor=unconfined",
        "--security-opt",
        "seccomp=unconfined",
        "--tmpfs",
        "/tmp:dev,exec,suid,noatime",
        "--env",
        "TMPDIR=/tmp",
        "--mount",
        f"type=bind,src={output_dir},dst=/output",
        image,
        "/opt/debuerreotype/examples/debian.sh",
    ]
    if arch:
        args += ["--arch", arch]
    return [*args, "/output", suite, timestamp]


def find_slim_rootfs(output_dir: Path, suite: str) -> Path:
    """debian.sh writes <serial>/<arch>/<suite>/slim/rootfs.tar.xz."""
    matches = sorted(output_dir.glob(f"*/*/{suite}/slim/rootfs.tar.xz"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"expected one {suite} slim rootfs under {output_dir}, found {len(matches)}"
        )
    return matches[0]


def sha256(path: Path) -> str:
    """Hex sha256 of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def rootfs_stem(suite: str, arch: str | None) -> str:
    """<suite>-slim for the host's arch, <suite>-slim-<arch> for an explicit --arch."""
    return f"{suite}-slim-{arch}" if arch else f"{suite}-slim"


def up_to_date(suite: str, timestamp: str, arch: str | None = None) -> bool:
    """True if sonicsort/rootfs already holds this suite/arch built at this timestamp."""
    meta = ROOTFS_DIR / f"{rootfs_stem(suite, arch)}.meta.json"
    tarball = ROOTFS_DIR / f"{rootfs_stem(suite, arch)}.tar.xz"
    if not (meta.exists() and tarball.exists()):
        return False
    recorded = json.loads(meta.read_text(encoding="utf-8"))
    return recorded.get("timestamp") == timestamp and recorded.get("sha256") == sha256(tarball)


def build(suite: str, timestamp: str, arch: str | None, force: bool) -> Path:
    """Build (or reuse) the slim rootfs; returns the tarball path under sonicsort/rootfs."""
    tarball = ROOTFS_DIR / f"{rootfs_stem(suite, arch)}.tar.xz"
    if not force and up_to_date(suite, timestamp, arch):
        print(f"{tarball.name} already built at {timestamp} -- skipping (--force to rebuild)")
        return tarball

    image = tool_image_tag()
    print(f"Building debuerreotype tool image {image}...", flush=True)
    subprocess.run(["docker", "build", "--pull", "--tag", image, str(FORK_ROOT)], check=True)

    with tempfile.TemporaryDirectory(prefix="debuerreotype-out-", dir=SONICSORT_DIR) as tmp:
        output_dir = Path(tmp)
        print(f"Bootstrapping {suite} at {timestamp} (snapshot.debian.org)...", flush=True)
        subprocess.run(run_args(image, output_dir, suite, timestamp, arch), check=True)
        built = find_slim_rootfs(output_dir, suite)
        built_arch = built.parts[-4]  # <serial>/<arch>/<suite>/slim/rootfs.tar.xz
        ROOTFS_DIR.mkdir(exist_ok=True)
        shutil.copyfile(built, tarball)

    meta = {
        "suite": suite,
        "variant": "slim",
        "timestamp": timestamp,
        "arch": arch or built_arch,
        "sha256": sha256(tarball),
        "debuerreotype": tool_image_tag().split(":", 1)[1],
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    (ROOTFS_DIR / f"{rootfs_stem(suite, arch)}.meta.json").write_text(
        json.dumps(meta, indent=1) + "\n", encoding="utf-8"
    )
    print(f"{tarball} ({tarball.stat().st_size // (1 << 20)} MiB, sha256 {meta['sha256'][:12]}...)")
    return tarball


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--suite", default="trixie", help="Debian suite/codename (default: trixie)")
    parser.add_argument(
        "--timestamp", help="snapshot.debian.org time (default: start of this ISO week, UTC)"
    )
    parser.add_argument("--arch", help="dpkg architecture (default: the Docker host's)")
    parser.add_argument(
        "--force", action="store_true", help="rebuild even if already built at this timestamp"
    )
    args = parser.parse_args(argv)

    build(args.suite, args.timestamp or week_start_timestamp(), args.arch, args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
