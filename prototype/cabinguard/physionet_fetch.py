"""Download open-access PhysioNet databases into a local data directory.

The AWS Open Data mirror (``physionet-open`` bucket) is tried first because
it is usually much faster; physionet.org is the fallback. Both serve
byte-identical releases, and every download is checked against the release's
``SHA256SUMS.txt`` when that file is present. Progress is printed per file.

Usage::

    python -m cabinguard.physionet_fetch drivedb szdb vfdb cudb --dest ../data
"""
from __future__ import annotations

import argparse
import hashlib
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

OFFICIAL = "https://physionet.org/files/{db}/{ver}/{name}"
MIRROR = "https://physionet-open.s3.amazonaws.com/{db}/{ver}/{name}"
MIRROR_LIST = "https://physionet-open.s3.amazonaws.com/?list-type=2&prefix={prefix}&max-keys=1000"

# Release versions of the databases CabinGuard uses.
VERSIONS = {
    "drivedb": "1.0.0",
    "szdb": "1.0.0",
    "vfdb": "1.0.0",
    "cudb": "1.0.0",
    "mitdb": "1.0.0",
    "accelerometry-walk-climb-drive": "1.0.0",
    "videopulse": "1.0.0",
}


def _get(url: str, timeout: float = 60.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (fixed hosts)
        return resp.read()


def _fetch(db: str, ver: str, name: str) -> bytes:
    # The AWS mirror serves the same release files and is usually much
    # faster than physionet.org; checksums are verified either way.
    errors = []
    for template in (MIRROR, OFFICIAL):
        url = template.format(db=db, ver=ver, name=name)
        try:
            return _get(url)
        except Exception as exc:  # network policy, 404, timeout
            errors.append(f"{url}: {exc}")
    raise OSError("; ".join(errors))


def list_files(db: str, ver: str) -> list[str]:
    """List release files from SHA256SUMS.txt, falling back to the mirror index."""
    try:
        sums = _fetch(db, ver, "SHA256SUMS.txt").decode()
        return [line.split(maxsplit=1)[1].strip() for line in sums.splitlines() if line.strip()]
    except OSError:
        pass
    prefix = f"{db}/{ver}/"
    names, token = [], None
    while True:
        url = MIRROR_LIST.format(prefix=urllib.parse.quote(prefix))
        if token:
            url += "&continuation-token=" + urllib.parse.quote(token)
        xml = _get(url).decode()
        names += [k[len(prefix):] for k in re.findall(r"<Key>([^<]*)</Key>", xml)]
        m = re.search(r"<NextContinuationToken>([^<]*)<", xml)
        if not m:
            return names
        token = m.group(1)


def fetch_database(db: str, dest: Path, pattern: str | None = None, workers: int = 8) -> Path:
    """Download one database release into ``dest/db`` and verify checksums."""
    ver = VERSIONS.get(db, "1.0.0")
    out_dir = dest / db
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        sums_text = _fetch(db, ver, "SHA256SUMS.txt").decode()
        sums = {n.strip(): h for h, n in (line.split(maxsplit=1) for line in sums_text.splitlines() if line.strip())}
    except OSError:
        sums = {}
    names = list(sums) or list_files(db, ver)
    if pattern:
        names = [n for n in names if re.search(pattern, n)]

    def one(name: str) -> str:
        target = out_dir / name
        if target.exists() and (name not in sums or hashlib.sha256(target.read_bytes()).hexdigest() == sums[name]):
            return "cached"
        data = _fetch(db, ver, name)
        if name in sums and hashlib.sha256(data).hexdigest() != sums[name]:
            raise OSError(f"checksum mismatch for {db}/{name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return "downloaded"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (name, status) in enumerate(zip(names, pool.map(one, names)), 1):
            print(f"  {db}: {i}/{len(names)} {status} {name}", flush=True)
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("databases", nargs="+")
    ap.add_argument("--dest", type=Path, default=Path(__file__).resolve().parents[2] / "data")
    ap.add_argument("--pattern", default=None, help="regex filter on file names")
    args = ap.parse_args()
    for db in args.databases:
        path = fetch_database(db, args.dest, args.pattern)
        print(f"{db}: {path}")


if __name__ == "__main__":
    main()
