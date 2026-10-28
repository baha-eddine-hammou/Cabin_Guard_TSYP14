"""Neck accelerometry around real clinical seizures from SeizeIT2 (OpenNeuro ds005873).

    python experiments/realdata/extract_seizeit2.py [--workers 16] [--background 6]

SeizeIT2 (Bhagubai et al., CC0) recorded 125 patients with focal epilepsy in
five epilepsy monitoring units with a wearable whose accelerometer sat on the
back of the neck, at 25 Hz, alongside video-EEG; seizures are annotated by
type from the video-EEG. Every motion file is several hours long, so only the
minutes around each annotated seizure, and a few background stretches per
recording, are fetched with HTTP range requests on the EDF records (1 s each).

For every seizure: the neck accelerometer from 60 s before onset to 60 s after
offset. For every recording: ``--background`` stretch(es) of 5 min that lie more
than 10 min from any seizure or impedance-check annotation. The raw 25 Hz
signal is stored; ``train_motion_real.py`` computes the branch features.

Output: ``data/derived/seizeit2_segments.npz`` (concatenated raw neck
acceleration in g with one entry per segment: subject, run, event type, onset
and duration relative to the segment start) and ``seizeit2_index.json``.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

DATA = HERE.parents[2] / "data"
DER = DATA / "derived"
CACHE = DATA / "seizeit2"
DS = "ds005873"
SNAPSHOT = "1.1.0"
S3 = "https://s3.amazonaws.com/openneuro.org/"
API = f"https://openneuro.org/crn/datasets/{DS}/snapshots/{SNAPSHOT}/files/"
NECK = ("EEG SD ACC X", "EEG SD ACC Y", "EEG SD ACC Z")
PRE_S, POST_S = 60.0, 60.0
BG_S, BG_GAP_S = 300.0, 600.0


# ------------------------------------------------------------------ HTTP ---
def _get(url: str, rng: tuple[int, int] | None = None, tries: int = 5) -> bytes:
    for k in range(tries):
        try:
            req = urllib.request.Request(url)
            if rng:
                req.add_header("Range", f"bytes={rng[0]}-{rng[1]}")
            with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 (fixed host)
                return r.read()
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2 ** k)
    raise RuntimeError("unreachable")


def _file_url(key: str) -> str:
    """Versioned S3 URL of a snapshot file, via the OpenNeuro file API redirect."""
    rel = key.split("/", 1)[1]
    req = urllib.request.Request(API + urllib.parse.quote(rel.replace("/", ":")), method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
        return r.url


def list_keys() -> list[tuple[str, int]]:
    cache = CACHE / "keys.json"
    if cache.exists():
        return [tuple(k) for k in json.loads(cache.read_text())]
    import re
    keys, tok = [], None
    while True:
        url = f"{S3}?list-type=2&prefix={DS}/" + (f"&continuation-token={urllib.parse.quote(tok)}" if tok else "")
        x = _get(url).decode()
        keys += list(zip(re.findall(r"<Key>(.*?)</Key>", x), map(int, re.findall(r"<Size>(.*?)</Size>", x))))
        m = re.search(r"<NextContinuationToken>(.*?)</NextContinuationToken>", x)
        if not m:
            break
        tok = m.group(1)
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(keys))
    return keys


# ------------------------------------------------------------------- EDF ---
class RemoteEDF:
    """Random access to the data records of a remote EDF+ file."""

    def __init__(self, url: str):
        self.url = url
        head = _get(url, (0, 255))
        self.header_bytes = int(head[184:192])
        self.n_records = int(head[236:244])
        self.record_s = float(head[244:252])
        ns = int(head[252:256])
        h = _get(url, (0, self.header_bytes - 1))

        def field(offset, width):
            return [h[offset + i * width: offset + (i + 1) * width].decode("latin-1").strip() for i in range(ns)]
        o = 256
        self.labels = field(o, 16)
        o += ns * (16 + 80)
        o += ns * 8                                   # physical dimension
        pmin = np.array(field(o, 8), float)
        o += ns * 8
        pmax = np.array(field(o, 8), float)
        o += ns * 8
        dmin = np.array(field(o, 8), float)
        o += ns * 8
        dmax = np.array(field(o, 8), float)
        o += ns * 8 + ns * 80
        self.nsamp = np.array(field(o, 8), int)
        self.gain = (pmax - pmin) / (dmax - dmin)
        self.offset = pmin - self.gain * dmin
        self.record_bytes = int(2 * self.nsamp.sum())
        self.ann = self.labels.index("EDF Annotations")

    def _records(self, first: int, count: int) -> np.ndarray:
        a = self.header_bytes + first * self.record_bytes
        raw = _get(self.url, (a, a + count * self.record_bytes - 1))
        return np.frombuffer(raw, "<i2").reshape(-1, self.record_bytes // 2)

    def _onset(self, rec: np.ndarray) -> float:
        start = int(self.nsamp[: self.ann].sum())
        tal = rec[start: start + self.nsamp[self.ann]].tobytes()
        return float(tal.split(b"\x14", 1)[0])

    def onset_of(self, i: int) -> float:
        return self._onset(self._records(i, 1)[0])

    def index_of(self, t: float) -> int:
        """Record holding time ``t`` (s from the recording start), allowing for gaps."""
        lo, hi = 0, self.n_records - 1
        i = int(min(max(t // self.record_s, 0), hi))
        if abs(self.onset_of(i) - (i * self.record_s)) < 1e-6:
            return i                                  # no gap before i: direct index
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.onset_of(mid) <= t:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def read(self, t0: float, t1: float, channels) -> tuple[np.ndarray, np.ndarray]:
        """Samples of ``channels`` between ``t0`` and ``t1`` and the onset of each record read."""
        i0, i1 = self.index_of(max(t0, 0.0)), self.index_of(t1)
        recs = self._records(i0, i1 - i0 + 1)
        onsets = np.array([self._onset(r) for r in recs])
        cols = []
        for ch in channels:
            c = self.labels.index(ch)
            a = int(self.nsamp[:c].sum())
            cols.append((recs[:, a: a + self.nsamp[c]].astype(float) * self.gain[c] + self.offset[c]).ravel())
        return np.stack(cols, axis=1), onsets


# ---------------------------------------------------------------- events ---
def read_events(key: str) -> list[dict]:
    p = CACHE / "events" / key.split("/")[-1]
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(_get(_file_url(key)))
    rows = p.read_text().splitlines()
    head = rows[0].split("\t")
    return [dict(zip(head, r.split("\t"))) for r in rows[1:] if r.strip()]


def run_windows(item, n_background: int, seed: int):
    mov_key, ev_key = item
    subject = mov_key.split("/")[1]
    run = mov_key.split("_run-")[1].split("_")[0]
    events = read_events(ev_key)
    seizures = [(float(e["onset"]), float(e["duration"]), e["eventType"]) for e in events
                if e["eventType"].startswith("sz")]
    busy = [(float(e["onset"]), float(e["onset"]) + float(e["duration"])) for e in events
            if e["eventType"].startswith(("sz", "impd"))]
    total = float(events[0]["recordingDuration"]) if events else 0.0
    if not seizures and n_background == 0:
        return []
    edf = RemoteEDF(_file_url(mov_key))
    if not set(NECK) <= set(edf.labels):
        return []
    fs = float(edf.nsamp[edf.labels.index(NECK[0])] / edf.record_s)
    out = []

    def segment(t0, t1, kind, onset, duration):
        x, onsets = edf.read(t0, t1, NECK)
        if len(onsets) > 1 and np.any(np.abs(np.diff(onsets) - edf.record_s) > 1e-6):
            return                                   # a gap inside the stretch: skip it
        start = float(onsets[0])
        out.append({"x": x.astype(np.float32), "fs": fs, "type": kind, "subject": subject, "run": run,
                    "onset": (onset - start) if onset is not None else np.nan, "duration": duration})

    for onset, dur, kind in seizures:
        segment(onset - PRE_S, onset + dur + POST_S, kind, onset, dur)
    rng = np.random.default_rng(seed)
    free = [t for t in np.arange(0, max(0.0, total - BG_S), 60.0)
            if all(t + BG_S < a - BG_GAP_S or t > b + BG_GAP_S for a, b in busy)]
    for t in rng.choice(free, size=min(n_background, len(free)), replace=False) if free else []:
        segment(float(t), float(t) + BG_S, "bckg", None, 0.0)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--background", type=int, default=1, help="5 min background stretches per recording")
    args = ap.parse_args()
    keys = [k for k, _ in list_keys()]
    movs = sorted(k for k in keys if k.endswith("_mov.edf"))
    items = [(m, m.replace("/mov/", "/eeg/").replace("_mov.edf", "_events.tsv")) for m in movs]
    have = set(keys)
    items = [it for it in items if it[1] in have]
    print(f"{len(items)} recordings with motion and annotations", flush=True)
    segs, done = [], 0
    with ProcessPoolExecutor(args.workers) as pool:
        futs = [pool.submit(run_windows, it, args.background, i) for i, it in enumerate(items)]
        for f in futs:
            try:
                segs += f.result()
            except Exception as exc:                # one unreadable file must not stop the rest
                print(f"  skipped: {exc}", flush=True)
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(items)} recordings, {len(segs)} segments", flush=True)
    DER.mkdir(parents=True, exist_ok=True)
    lengths = np.array([len(s["x"]) for s in segs])
    np.savez_compressed(
        DER / "seizeit2_segments.npz", x=np.vstack([s["x"] for s in segs]),
        start=np.concatenate([[0], np.cumsum(lengths)[:-1]]), length=lengths,
        fs=np.array([s["fs"] for s in segs]), type=np.array([s["type"] for s in segs]),
        subject=np.array([s["subject"] for s in segs]), run=np.array([s["run"] for s in segs]),
        onset=np.array([s["onset"] for s in segs]), duration=np.array([s["duration"] for s in segs]))
    kinds = {}
    for s in segs:
        kinds[s["type"]] = kinds.get(s["type"], 0) + 1
    (DER / "seizeit2_index.json").write_text(json.dumps({"segments_by_type": kinds,
                                                         "subjects": len({s["subject"] for s in segs})}, indent=1))
    print(kinds)


if __name__ == "__main__":
    main()
