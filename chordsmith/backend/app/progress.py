"""How far along the long jobs are.

Separation takes tens of minutes and the queue is served one song at a time, so
"separando…" with no number is not information — it is the same word for four
minutes in and for forty. What a person actually wants to know is which stage
it reached, how long it has been going, and how many songs are ahead of theirs.

Held in memory rather than in the database on purpose: it is worth nothing after
a restart, it changes many times a second, and writing that to SQLite would put
a disk write on the path of a progress bar.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class Job:
    song_id: str
    kind: str  # "stems" | "lyrics" | "tracks" | "variant"
    stage: str = ""
    #: 0–1 within the current stage, or None when the stage cannot report it.
    fraction: float | None = None
    #: Which stage of how many, for work that runs in known phases.
    step: int = 0
    steps: int = 0
    started_at: float = field(default_factory=time.time)

    @property
    def elapsed(self) -> float:
        return time.time() - self.started_at

    def to_dict(self) -> dict:
        # Overall progress across the whole job, not just the current stage:
        # a bar that fills to 100% and then starts over at stage two is worse
        # than no bar, because it promises an ending that is not coming.
        overall: float | None = None
        if self.steps:
            done = max(0, self.step - 1) / self.steps
            within = (self.fraction or 0) / self.steps
            overall = min(1.0, done + within)
        elif self.fraction is not None:
            overall = self.fraction

        return {
            "songId": self.song_id,
            "kind": self.kind,
            "stage": self.stage,
            "step": self.step,
            "steps": self.steps,
            "fraction": round(self.fraction, 3) if self.fraction is not None else None,
            "overall": round(overall, 3) if overall is not None else None,
            "elapsedSeconds": round(self.elapsed, 1),
        }


_lock = threading.Lock()
_running: dict[str, Job] = {}
_queued: dict[str, list[str]] = {"stems": [], "lyrics": [], "tracks": [], "variant": []}


def enqueued(song_id: str, kind: str) -> None:
    with _lock:
        queue = _queued.setdefault(kind, [])
        if song_id not in queue:
            queue.append(song_id)


def start(song_id: str, kind: str, steps: int = 0) -> Job:
    with _lock:
        queue = _queued.setdefault(kind, [])
        if song_id in queue:
            queue.remove(song_id)
        job = Job(song_id=song_id, kind=kind, steps=steps)
        _running[f"{kind}:{song_id}"] = job
        return job


def stage(song_id: str, kind: str, name: str, step: int = 0) -> None:
    with _lock:
        job = _running.get(f"{kind}:{song_id}")
        if job:
            job.stage = name
            job.fraction = None
            if step:
                job.step = step


def advance(song_id: str, kind: str, fraction: float) -> None:
    with _lock:
        job = _running.get(f"{kind}:{song_id}")
        if job:
            job.fraction = max(0.0, min(1.0, fraction))


def finish(song_id: str, kind: str) -> None:
    with _lock:
        _running.pop(f"{kind}:{song_id}", None)
        queue = _queued.setdefault(kind, [])
        if song_id in queue:
            queue.remove(song_id)


def for_song(song_id: str) -> dict:
    """Everything known about this song's long jobs, running or waiting."""
    with _lock:
        running = [job.to_dict() for key, job in _running.items() if key.endswith(f":{song_id}")]
        waiting = {}
        for kind, queue in _queued.items():
            if song_id in queue:
                # One-based: "1 na fila" reads as next, which is what it means.
                waiting[kind] = queue.index(song_id) + 1
    return {"running": running, "waiting": waiting}


def snapshot() -> dict:
    """The whole picture, for a library that wants to show its own backlog."""
    with _lock:
        return {
            "running": [job.to_dict() for job in _running.values()],
            "queued": {kind: len(queue) for kind, queue in _queued.items() if queue},
        }
