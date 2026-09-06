"""One-command publish loop (Plan B Task B1): spacing guard, sweeps, gates, commit.

This orchestrator never re-implements an entry point: it subprocesses the existing ones
(``make sweep``, ``main.py --source ba --panel``, ``make check``, ``make live-site``,
``make export-app``, ``scripts.release_check``) in the runbook's order. The laws it must
obey (.kilo/plans/1788618000000-local-sweep-automation-plan.md):

1. **Never commit a red gate.** Any failing step stops the run before ``git commit``,
   exits non-zero, and leaves the evidence in ``logs/auto/<run id>.log``.
2. ``data/raw/`` is append-only; the only writes to it are the collectors' own sweeps.
3. Spacing: a BA panel sweep is ~1,320 paced requests over ~40 min and never starts when
   the newest BA partition is under 20 h old; JobTech sweeps are cheap (7 pages) but the
   design cadence is at most twice daily - 2 h minimum.
4. The release check runs DIRECTLY on the built page, never via ``make release-check``:
   that target depends on ``site``, which rebuilds the synthetic page over the live one.
5. Log to ``logs/auto/<YYYYMMDDTHHMMSSZ>.log`` (gitignored). Subprocess output lands in
   the log only; on failure its tail is printed to stderr for diagnosis.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
COLLECTIONS_DIR = ROOT / "data" / "raw" / "collections"
AUTO_LOG_DIR = ROOT / "logs" / "auto"
PAGE_BUILD = ROOT / "site" / "build" / "index.html"
PAGE_LIVE = ROOT / "docs" / "index.html"
# The only paths an auto run may commit: the audit page and the app's export. The commit
# itself is pathspec-scoped, so unrelated staged work can never ride along.
ARTEFACTS = ("docs/index.html", "app/data.json")

# Minimum hours between sweeps, per source (plan law 3).
SPACING_HOURS: dict[str, float] = {"jobtech": 2.0, "ba": 20.0}

SWEEP_LABEL = {"jobtech": "jobtech sweep", "ba": "ba panel sweep"}


class StepFailure(Exception):
    """A step exited non-zero; the run must stop before the commit."""


@dataclass(frozen=True)
class ScopeState:
    """What --status and the spacing guard need to know about one stored scope."""

    source: str
    scope_id: str
    sweeps: int
    newest_started: datetime | None
    freshness_threshold_hours: float | None


class RunLog:
    """Timestamped run lines to logs/auto/<run id>.log, mirrored to stdout."""

    def __init__(self, run_id: str) -> None:
        AUTO_LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.path = AUTO_LOG_DIR / f"{run_id}.log"
        self._file = self.path.open("w", encoding="utf-8", newline="\n")

    def close(self) -> None:
        self._file.close()

    @property
    def handle(self) -> TextIO:
        """Subprocess stdout target: their output stays in the log, never on stdout."""
        return self._file

    def line(self, text: str) -> None:
        stamp = datetime.now(UTC).strftime("%H:%M:%SZ")
        entry = f"[{stamp}] {text}"
        self._file.write(entry + "\n")
        self._file.flush()
        print(entry, flush=True)

    def tail(self, lines: int) -> str:
        self._file.flush()
        # errors="replace": sweep subprocesses write Windows-encoded bytes (German
        # umlauts) into the log; status output must never crash on mixed encodings.
        return "".join(
            self.path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)[
                -lines:
            ]
        )


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def scope_states() -> list[ScopeState]:
    """One row per stored (source, scope_id): sweep count, newest start, threshold."""
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for path in COLLECTIONS_DIR.glob("*/*/*/manifest.json"):
        manifest: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        key = (str(manifest.get("source", "")), str(manifest.get("scope_id", "")))
        grouped.setdefault(key, []).append(manifest)
    states: list[ScopeState] = []
    for (source, scope_id), manifests in sorted(grouped.items()):
        started = [
            _parse_utc(str(entry["started_at"]))
            for entry in manifests
            if isinstance(entry.get("started_at"), str)
        ]
        newest_started = max(started) if started else None
        threshold = None
        for entry in manifests:
            if newest_started is None or not isinstance(entry.get("started_at"), str):
                continue
            if _parse_utc(str(entry["started_at"])) == newest_started:
                raw = entry.get("freshness_threshold_hours")
                if isinstance(raw, (int, float)):
                    threshold = float(raw)
        states.append(ScopeState(source, scope_id, len(manifests), newest_started, threshold))
    return states


def spacing_guard(source: str, log: RunLog) -> bool:
    """Plan law 3: refuse to sweep a source whose newest partition is too fresh."""
    minimum = SPACING_HOURS[source]
    started = [
        state.newest_started
        for state in scope_states()
        if state.source == source and state.newest_started is not None
    ]
    if not started:
        log.line(f"spacing guard {source}: no stored partitions yet; sweep allowed")
        return True
    newest = max(started)
    age = (datetime.now(UTC) - newest).total_seconds() / 3600
    if age < minimum:
        log.line(
            f"spacing guard {source}: newest partition {newest:%Y-%m-%dT%H:%M:%SZ} is "
            f"{age:.1f} h old (minimum {minimum:.0f} h); refusing to sweep"
        )
        return False
    log.line(
        f"spacing guard {source}: newest partition {newest:%Y-%m-%dT%H:%M:%SZ} is "
        f"{age:.1f} h old; sweep allowed"
    )
    return True


def run_step(name: str, command: list[str], log: RunLog, dry_run: bool) -> None:
    """Run one entry point; any non-zero exit stops the run before the commit."""
    log.line(f"step {name}: {subprocess.list2cmdline(command)}")
    if dry_run:
        log.line("dry run: skipping execution")
        return
    log._file.flush()
    completed = subprocess.run(command, cwd=ROOT, stdout=log.handle, stderr=subprocess.STDOUT)
    if completed.returncode != 0:
        log.line(f"FAILED step {name} (exit {completed.returncode}); stopping before commit")
        sys.stderr.write(log.tail(15))
        raise StepFailure(name)


def sweep_command(source: str) -> list[str]:
    if source == "jobtech":
        return ["make", "sweep"]
    date = datetime.now(UTC).date().isoformat()
    return [
        "uv",
        "run",
        "--offline",
        "python",
        "main.py",
        "--source",
        "ba",
        "--panel",
        "--date",
        date,
    ]


def export_app_available() -> bool:
    """`make -n` parses the Makefile and prints the recipe without running anything; a
    missing target exits non-zero, which is the plan's skip-with-a-logged-warning case."""
    probe = subprocess.run(
        ["make", "-n", "export-app"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return probe.returncode == 0


def commit_artefacts(message: str, log: RunLog, dry_run: bool) -> bool:
    """Commit the refreshed artefacts; a green run with unchanged artefacts is success."""
    if dry_run:
        probe = subprocess.run(
            ["git", "status", "--porcelain", "--", *ARTEFACTS],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        log.line(f"dry run: would commit: {probe.stdout.strip() or '(no artefact changes)'}")
        return False
    run_step("git add artefacts", ["git", "add", "--", *ARTEFACTS], log, dry_run=False)
    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", *ARTEFACTS], cwd=ROOT, check=False
    )
    if staged.returncode == 0:
        log.line("no artefact changes; nothing to commit")
        return False
    if staged.returncode != 1:
        log.line(f"FAILED git diff --cached (exit {staged.returncode}); stopping before commit")
        raise StepFailure("git diff --cached")
    run_step("git commit", ["git", "commit", "-m", message, "--", *ARTEFACTS], log, dry_run=False)
    return True


def run_loop(sources: list[str], args: argparse.Namespace, run_id: str, log: RunLog) -> None:
    if not args.skip_sweep:
        for source in sources:
            if not spacing_guard(source, log):
                raise StepFailure(f"spacing guard {source}")
        # check-before-sweep (recorded constraint): a sweep collected with a broken
        # mapping bakes the error into a permanent partition, so the gate runs first.
        # The plan's post-sweep `make check` below still runs: unattended redundancy on
        # the one command that protects permanent data is deliberate.
        run_step("pre-sweep make check", ["make", "check"], log, args.dry_run)
        for source in sources:
            if source == "ba":
                log.line("ba panel sweep is ~40 min; its output lands in this log only")
            run_step(f"sweep {source}", sweep_command(source), log, args.dry_run)
            if source == "ba":
                run_step(
                    "ba panel DoD gate",
                    ["uv", "run", "--offline", "python", "scripts/check_ba_panel_readiness.py"],
                    log,
                    args.dry_run,
                )
    else:
        log.line("--skip-sweep: running gates + publish only")

    run_step("make check", ["make", "check"], log, args.dry_run)
    run_step("make live-site", ["make", "live-site"], log, args.dry_run)
    if export_app_available():
        run_step("make export-app", ["make", "export-app"], log, args.dry_run)
    else:
        log.line(
            "WARNING: no export-app target in Makefile yet (Plan A A2); "
            "skipping the app surface this run"
        )
    run_step(
        "release check (live page)",
        [
            "uv",
            "run",
            "--offline",
            "python",
            "-m",
            "scripts.release_check",
            "site/build/index.html",
        ],
        log,
        args.dry_run,
    )

    log.line(f"copy {PAGE_BUILD} -> {PAGE_LIVE}")
    if args.dry_run:
        log.line("dry run: skipping execution")
    elif PAGE_BUILD.is_file():
        shutil.copyfile(PAGE_BUILD, PAGE_LIVE)
    else:
        log.line(f"FAILED step copy page: {PAGE_BUILD} does not exist; stopping before commit")
        raise StepFailure("copy page")

    states = scope_states()
    sweep_total = sum(state.sweeps for state in states)
    scope_total = len(states)
    description = (
        "skip-sweep gates + publish"
        if args.skip_sweep
        else " + ".join(SWEEP_LABEL[s] for s in sources)
    )
    message = (
        f"docs(artifact): auto run {run_id} - {description}; gates green; "
        f"page + app export re-synced ({sweep_total} sweeps, {scope_total} scopes)"
    )
    committed = commit_artefacts(message, log, args.dry_run)

    if args.push:
        if committed:
            run_step("git push", ["git", "push"], log, args.dry_run)
        else:
            log.line("nothing committed; nothing to push")


def parse_sources(raw: str) -> list[str]:
    sources: list[str] = []
    for part in raw.split(","):
        source = part.strip()
        if not source:
            continue
        if source not in SPACING_HOURS:
            raise SystemExit(f"unknown source {source!r}; expected: {', '.join(SPACING_HOURS)}")
        if source not in sources:
            sources.append(source)
    if not sources:
        raise SystemExit("no sources given")
    return sources


def status_mode() -> int:
    now = datetime.now(UTC)
    print(f"auto status {now:%Y-%m-%dT%H:%M:%SZ}")
    states = scope_states()
    if not states:
        print("no stored partitions under data/raw/collections/")
    for state in states:
        if state.newest_started is None:
            print(
                f"{state.source}/{state.scope_id}: {state.sweeps} sweep(s); no parseable start time"
            )
            continue
        age = (now - state.newest_started).total_seconds() / 3600
        minimum = SPACING_HOURS.get(state.source)
        if minimum is None:
            spacing = "no cadence rule for this source"
        elif age >= minimum:
            spacing = f"sweep allowed (min {minimum:.0f} h)"
        else:
            spacing = f"sweep blocked, {minimum - age:.1f} h to go (min {minimum:.0f} h)"
        threshold = state.freshness_threshold_hours
        if threshold is None:
            freshness = "unknown freshness threshold"
        else:
            freshness = f"{'fresh' if age <= threshold else 'stale'} (threshold {threshold:.0f} h)"
        print(
            f"{state.source}/{state.scope_id}: {state.sweeps} sweep(s); "
            f"newest {state.newest_started:%Y-%m-%dT%H:%M:%SZ} ({age:.1f} h old); "
            f"{spacing}; {freshness}"
        )
    logs = sorted(AUTO_LOG_DIR.glob("*.log"))
    if logs:
        print(f"newest auto log: {logs[-1].name}")
        # errors="replace" as in RunLog.tail: BA sweep output contains
        # Windows-encoded bytes; the status tail must not crash on them.
        for line in logs[-1].read_text(encoding="utf-8", errors="replace").splitlines()[-15:]:
            print(line)
    else:
        print("no auto logs yet")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--sources",
        default="jobtech",
        help=f"comma-separated sources to sweep (default: jobtech; one of: "
        f"{', '.join(SPACING_HOURS)})",
    )
    parser.add_argument("--skip-sweep", action="store_true", help="gates + publish only, no sweeps")
    parser.add_argument("--push", action="store_true", help="git push after a successful commit")
    parser.add_argument("--dry-run", action="store_true", help="log every step, execute none")
    parser.add_argument(
        "--status", action="store_true", help="print partition ages, verdicts, newest log tail"
    )
    args = parser.parse_args(argv)
    if args.status:
        return status_mode()
    sources = parse_sources(args.sources)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log = RunLog(run_id)
    try:
        log.line(
            f"auto run {run_id} sources={','.join(sources)} "
            f"skip_sweep={args.skip_sweep} push={args.push} dry_run={args.dry_run}"
        )
        try:
            run_loop(sources, args, run_id, log)
        except StepFailure as failure:
            log.line(f"auto run {run_id} STOPPED at {failure}; nothing committed")
            return 1
        log.line(f"auto run {run_id} COMPLETE")
        return 0
    finally:
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
