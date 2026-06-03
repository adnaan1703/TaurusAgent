from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, TextIO

ProgressEventCallback = Callable[[str, Mapping[str, object]], None]

_FALSE_VALUES = {"0", "false", "no", "off", "none", "disabled"}
_PLAIN_VALUES = {"plain", "log", "logs", "text"}
_RICH_VALUES = {"rich", "true", "1", "yes", "on"}


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    description: str
    details: str
    completed: int | None = None
    total: int | None = None


class ProgressReporter(Protocol):
    def __call__(self, event: str, payload: Mapping[str, object]) -> None:
        ...

    def close(self) -> None:
        ...

    def fail(self, exc: BaseException) -> None:
        ...


def emit_progress(
    progress: ProgressEventCallback | None,
    event: str,
    **payload: object,
) -> None:
    if progress is not None:
        progress(event, payload)


def create_progress_reporter(
    command: str,
    *,
    env: Mapping[str, str] | None = None,
    stream: TextIO | None = None,
    force_interactive: bool | None = None,
) -> "_ProgressContext":
    resolved_env = os.environ if env is None else env
    resolved_stream = stream or sys.stderr
    mode = _resolve_progress_mode(
        resolved_env.get("TAURUS_PROGRESS", "auto"),
        stream=resolved_stream,
        force_interactive=force_interactive,
    )
    if mode == "disabled":
        reporter: ProgressReporter = NullProgressReporter()
    elif mode == "rich":
        reporter = RichProgressReporter(command, stream=resolved_stream)
    else:
        reporter = PlainProgressReporter(command, stream=resolved_stream)
    return _ProgressContext(reporter)


def format_rich_progress_snapshot(
    command: str,
    event: str,
    payload: Mapping[str, object],
) -> ProgressSnapshot | None:
    if command == "import-kite-candles":
        return _import_snapshot(event, payload)
    if command == "compute-graph-stats":
        return _graph_snapshot(event, payload)
    if command in {"paper-loop", "paper-loop-kite"}:
        return _paper_loop_snapshot(command, event, payload)
    return _generic_snapshot(command, event, payload)


def format_plain_progress_line(
    command: str,
    event: str,
    payload: Mapping[str, object],
    *,
    elapsed_seconds: float,
    eta_seconds: float | None,
) -> str | None:
    snapshot = format_rich_progress_snapshot(command, event, payload)
    if snapshot is None:
        return None

    parts = [
        "taurus progress",
        f"{command}:",
        snapshot.details,
    ]
    if snapshot.completed is not None and snapshot.total is not None:
        percent = _percent(snapshot.completed, snapshot.total)
        parts.append(f"progress={snapshot.completed}/{snapshot.total}")
        parts.append(f"percent={percent:.1f}")
    parts.append(f"elapsed={_format_duration(elapsed_seconds)}")
    parts.append(f"eta={_format_duration(eta_seconds) if eta_seconds is not None else 'unknown'}")
    return " ".join(part for part in parts if part)


class _ProgressContext:
    def __init__(self, reporter: ProgressReporter) -> None:
        self._reporter = reporter

    def __enter__(self) -> ProgressReporter:
        return self._reporter

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        if exc is not None:
            self._reporter.fail(exc)
        self._reporter.close()
        return False


class NullProgressReporter:
    def __call__(self, event: str, payload: Mapping[str, object]) -> None:
        return None

    def close(self) -> None:
        return None

    def fail(self, exc: BaseException) -> None:
        return None


class PlainProgressReporter:
    def __init__(
        self,
        command: str,
        *,
        stream: TextIO,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.command = command
        self.stream = stream
        self._now = now or time.monotonic
        self._started_at = self._now()

    def __call__(self, event: str, payload: Mapping[str, object]) -> None:
        snapshot = format_rich_progress_snapshot(self.command, event, payload)
        if snapshot is None:
            return
        elapsed = self._now() - self._started_at
        line = format_plain_progress_line(
            self.command,
            event,
            payload,
            elapsed_seconds=elapsed,
            eta_seconds=_estimate_eta(elapsed, snapshot.completed, snapshot.total),
        )
        if line is not None:
            self.stream.write(f"{line}\n")
            self.stream.flush()

    def close(self) -> None:
        return None

    def fail(self, exc: BaseException) -> None:
        elapsed = self._now() - self._started_at
        self.stream.write(
            "taurus progress "
            f"{self.command}: failed error_type={exc.__class__.__name__} "
            f"message={str(exc)} elapsed={_format_duration(elapsed)}\n"
        )
        self.stream.flush()


class RichProgressReporter:
    def __init__(self, command: str, *, stream: TextIO) -> None:
        from rich.console import Console
        from rich.progress import (
            BarColumn,
            Progress,
            TaskProgressColumn,
            TextColumn,
            TimeElapsedColumn,
            TimeRemainingColumn,
        )

        self.command = command
        self.console = Console(file=stream, stderr=True)
        self.progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.completed:.0f}/{task.total:.0f}"),
            TextColumn("{task.fields[details]}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=self.console,
            transient=False,
        )
        self._task_id: int | None = None
        self.progress.start()

    def __call__(self, event: str, payload: Mapping[str, object]) -> None:
        snapshot = format_rich_progress_snapshot(self.command, event, payload)
        if snapshot is None:
            return
        total = snapshot.total if snapshot.total is not None else 1
        completed = snapshot.completed if snapshot.completed is not None else 0
        if self._task_id is None:
            self._task_id = self.progress.add_task(
                snapshot.description,
                total=total,
                completed=completed,
                details=snapshot.details,
            )
            return
        self.progress.update(
            self._task_id,
            description=snapshot.description,
            total=total,
            completed=completed,
            details=snapshot.details,
        )

    def close(self) -> None:
        self.progress.stop()

    def fail(self, exc: BaseException) -> None:
        self.console.print(
            f"[red]failed[/red] error_type={exc.__class__.__name__} message={str(exc)}"
        )


def _resolve_progress_mode(
    value: str,
    *,
    stream: TextIO,
    force_interactive: bool | None,
) -> str:
    normalized = value.strip().lower()
    if normalized in _FALSE_VALUES:
        return "disabled"
    if normalized in _PLAIN_VALUES:
        return "plain"
    if normalized == "auto" or normalized in _RICH_VALUES:
        is_interactive = force_interactive if force_interactive is not None else stream.isatty()
        return "rich" if is_interactive else "plain"
    return "rich" if stream.isatty() else "plain"


def _import_snapshot(event: str, payload: Mapping[str, object]) -> ProgressSnapshot | None:
    if event == "import.setup_started":
        stage = _string(payload, "stage", "setup")
        return ProgressSnapshot("import-kite-candles", f"stage={stage}", 0, 1)
    if event == "import.started":
        total = _int(payload, "total", 0)
        return ProgressSnapshot("import-kite-candles", f"symbols={total} cumulative=0", 0, total)
    if event in {"import.symbol_started", "import.symbol_completed"}:
        current = _int(payload, "current", 0)
        total = _int(payload, "total", 0)
        symbol = _string(payload, "symbol", "-")
        candles = _int(payload, "candles", 0)
        cumulative = _int(payload, "cumulative_candles", 0)
        completed = current if event.endswith("completed") else max(current - 1, 0)
        details = (
            f"symbol={symbol} current={current}/{total} "
            f"candles={candles} cumulative={cumulative}"
        )
        return ProgressSnapshot("import-kite-candles", details, completed, total)
    if event == "import.completed":
        total = _int(payload, "total", 0)
        cumulative = _int(payload, "cumulative_candles", 0)
        return ProgressSnapshot(
            "import-kite-candles",
            f"symbols={total} cumulative={cumulative}",
            total,
            total,
        )
    return None


def _graph_snapshot(event: str, payload: Mapping[str, object]) -> ProgressSnapshot | None:
    if event == "graph.stats.started":
        edge_count = _int(payload, "edge_count", 0)
        window_count = _int(payload, "window_count", 0)
        total = _int(payload, "total", edge_count * window_count)
        return ProgressSnapshot(
            "compute-graph-stats",
            f"edges={edge_count} windows={window_count}",
            0,
            total,
        )
    if event in {"graph.stats.window_started", "graph.stats.window_completed"}:
        current = _int(payload, "current", 0)
        total = _int(payload, "total", 0)
        edge_key = _string(payload, "edge_key", "-")
        source = _string(payload, "source_symbol", "-")
        target = _string(payload, "target_symbol", "-")
        window = _string(payload, "window", "-")
        validated = _int(payload, "validated_count", 0)
        insufficient = _int(payload, "insufficient_count", 0)
        promoted = _int(payload, "promoted_count", 0)
        completed = current if event.endswith("completed") else max(current - 1, 0)
        details = (
            f"edge={edge_key} source={source} target={target} window={window} "
            f"current={current}/{total} validated={validated} "
            f"insufficient={insufficient} promoted={promoted}"
        )
        return ProgressSnapshot("compute-graph-stats", details, completed, total)
    if event == "graph.stats.completed":
        total = _int(payload, "total", _int(payload, "stats_upserted", 0))
        validated = _int(payload, "validated_count", 0)
        insufficient = _int(payload, "insufficient_count", 0)
        promoted = _int(payload, "promoted_count", 0)
        details = (
            f"stats={total} validated={validated} "
            f"insufficient={insufficient} promoted={promoted}"
        )
        return ProgressSnapshot("compute-graph-stats", details, total, total)
    return None


def _paper_loop_snapshot(
    command: str,
    event: str,
    payload: Mapping[str, object],
) -> ProgressSnapshot | None:
    symbol_count = max(_int(payload, "symbol_count", 1), 1)
    if event == "paper.loop.started":
        iterations = _int(payload, "iterations", 1)
        symbols = _symbols(payload)
        return ProgressSnapshot(
            command,
            f"iterations={iterations} selected_symbols={symbols}",
            0,
            iterations * symbol_count,
        )
    if event == "paper.iteration.started":
        iteration = _int(payload, "iteration", 1)
        iterations = _int(payload, "iterations", 1)
        total = iterations * symbol_count
        completed = max(iteration - 1, 0) * symbol_count
        return ProgressSnapshot(
            command,
            f"iteration={iteration}/{iterations} selected_symbols={_symbols(payload)}",
            completed,
            total,
        )
    if event in {"paper.run.started", "paper.run.setup_started", "paper.run.setup_completed"}:
        iteration = _int(payload, "iteration", 1)
        iterations = _int(payload, "iterations", 1)
        total = iterations * symbol_count
        completed = max(iteration - 1, 0) * symbol_count
        run_id = _string(payload, "run_id", "pending")
        stage = _string(payload, "stage", "run")
        return ProgressSnapshot(
            command,
            f"iteration={iteration}/{iterations} run_id={run_id} "
            f"stage={stage} selected_symbols={_symbols(payload)}",
            completed,
            total,
        )
    if event == "paper.run.failed":
        iteration = _int(payload, "iteration", 1)
        iterations = _int(payload, "iterations", 1)
        total = iterations * symbol_count
        completed = max(iteration - 1, 0) * symbol_count
        run_id = _string(payload, "run_id", "-")
        stage = _string(payload, "stage", "run")
        error_type = _string(payload, "error_type", "-")
        message = _string(payload, "message", "")
        return ProgressSnapshot(
            command,
            f"iteration={iteration}/{iterations} run_id={run_id} "
            f"stage={stage} error_type={error_type} message={message}",
            completed,
            total,
        )
    if event in {"paper.symbol.stage_started", "paper.symbol.completed", "paper.symbol.failed"}:
        iteration = _int(payload, "iteration", 1)
        iterations = _int(payload, "iterations", 1)
        symbol_index = _int(payload, "symbol_index", 1)
        total = iterations * symbol_count
        base = max(iteration - 1, 0) * symbol_count
        completed = base + (
            symbol_index if event in {"paper.symbol.completed", "paper.symbol.failed"} else symbol_index - 1
        )
        run_id = _string(payload, "run_id", "pending")
        symbol = _string(payload, "symbol", "-")
        stage = _string(
            payload,
            "terminal_stage",
            _string(payload, "stage", "symbol_pipeline"),
        )
        succeeded = _int(payload, "succeeded_count", 0)
        failed = _int(payload, "failed_count", 0)
        return ProgressSnapshot(
            command,
            f"iteration={iteration}/{iterations} run_id={run_id} "
            f"symbol={symbol} stage={stage} succeeded={succeeded} failed={failed}",
            min(completed, total),
            total,
        )
    if event == "paper.iteration.completed":
        iteration = _int(payload, "iteration", 1)
        iterations = _int(payload, "iterations", 1)
        total = iterations * symbol_count
        completed = min(iteration * symbol_count, total)
        return ProgressSnapshot(
            command,
            f"iteration={iteration}/{iterations} run_id={_string(payload, 'run_id', '-')} "
            f"status={_string(payload, 'status', '-')} "
            f"succeeded={_int(payload, 'succeeded_count', 0)} "
            f"failed={_int(payload, 'failed_count', 0)}",
            completed,
            total,
        )
    if event == "paper.loop.completed":
        iterations = _int(payload, "iterations", 1)
        total = iterations * symbol_count
        return ProgressSnapshot(command, f"iterations={iterations} completed=true", total, total)
    return None


def _generic_snapshot(
    command: str,
    event: str,
    payload: Mapping[str, object],
) -> ProgressSnapshot | None:
    detail = " ".join(f"{key}={value}" for key, value in sorted(payload.items()))
    return ProgressSnapshot(command, f"event={event} {detail}".strip(), None, None)


def _estimate_eta(
    elapsed_seconds: float,
    completed: int | None,
    total: int | None,
) -> float | None:
    if completed is None or total is None or completed <= 0 or total <= completed:
        return 0.0 if completed is not None and total is not None and total <= completed else None
    return (elapsed_seconds / completed) * (total - completed)


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    if seconds < 1:
        return f"{seconds:.1f}s"
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, remaining = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m{remaining:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def _percent(completed: int, total: int) -> float:
    if total <= 0:
        return 100.0
    return min(max((completed / total) * 100, 0.0), 100.0)


def _int(payload: Mapping[str, object], key: str, default: int) -> int:
    value = payload.get(key, default)
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _string(payload: Mapping[str, object], key: str, default: str) -> str:
    value = payload.get(key)
    if value is None:
        return default
    text = str(value)
    return text if text else default


def _symbols(payload: Mapping[str, object]) -> str:
    value = payload.get("symbols")
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(item) for item in value)
    return "-"
