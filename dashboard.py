#!/usr/bin/env python3
"""Logger Dashboard — a polished CLI front-end for the Logs logging utility.

Modes:
    python3 dashboard.py            # interactive menu loop
    python3 dashboard.py --demo     # scripted, non-interactive showcase (exits 0)
    python3 dashboard.py --help     # argparse help

Every menu action drives a REAL capability of the Logs class in Logger.py:
    (1) interactive log composer -> Logs.LogsMessages
    (2) demo: write sample logs across all levels -> Logs.LogsMessages, then print files
    (3) tail/preview a chosen log file
    (4) show where logs are written

The dashboard is EOF/pipe-safe: piping /dev/null exits promptly instead of looping.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

# Make sure we can import the sibling Logger module regardless of CWD.
PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from Logger import Logs, LEVEL_MAP  # noqa: E402

APP_NAME = "Logger"
TAGLINE = "A stdlib-only leveled file logger with a friendly cockpit."
LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# ---------------------------------------------------------------------------
# Optional rich UI with a clean plain-ANSI fallback.
# ---------------------------------------------------------------------------
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt
    from rich.text import Text

    _console = Console()
    _HAVE_RICH = True
except Exception:  # pragma: no cover - exercised only when rich is missing
    _console = None
    _HAVE_RICH = False


# Plain-ANSI color helpers (used both for fallback and small accents).
class _C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    CYAN = "\033[36m"
    YELLOW = "\033[33m"
    MAGENTA = "\033[35m"


LEVEL_COLORS = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold red",
}


def out(msg: str = "") -> None:
    if _HAVE_RICH:
        _console.print(msg)
    else:
        print(msg)


def success(msg: str) -> None:
    if _HAVE_RICH:
        _console.print(f"[bold green]OK[/] {msg}")
    else:
        print(f"{_C.GREEN}OK{_C.RESET} {msg}")


def failure(msg: str) -> None:
    if _HAVE_RICH:
        _console.print(f"[bold red]ERR[/] {msg}")
    else:
        print(f"{_C.RED}ERR{_C.RESET} {msg}")


def banner() -> None:
    if _HAVE_RICH:
        title = Text(APP_NAME, style="bold magenta")
        title.append("  ")
        title.append(TAGLINE, style="italic dim")
        _console.print(Panel(title, border_style="magenta", padding=(0, 2)))
    else:
        line = "=" * 60
        print(f"{_C.MAGENTA}{_C.BOLD}{line}")
        print(f"  {APP_NAME} — {TAGLINE}")
        print(f"{line}{_C.RESET}")


def status_panel() -> None:
    """Summarize where logs live and what levels exist."""
    main_file = PROJECT_DIR / "main.log"
    known_logs = sorted(str(p.relative_to(PROJECT_DIR))
                        for p in PROJECT_DIR.rglob("*.log"))
    if _HAVE_RICH:
        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("Setting", style="dim")
        table.add_column("Value")
        table.add_row("Project dir", str(PROJECT_DIR))
        table.add_row("Main log", str(main_file))
        table.add_row("Levels", ", ".join(LEVELS))
        table.add_row("Existing .log files", str(len(known_logs)))
        _console.print(Panel(table, title="Status", border_style="cyan",
                             padding=(0, 1)))
    else:
        print(f"{_C.CYAN}Status{_C.RESET}")
        print(f"  Project dir : {PROJECT_DIR}")
        print(f"  Main log    : {main_file}")
        print(f"  Levels      : {', '.join(LEVELS)}")
        print(f"  .log files  : {len(known_logs)}")


def menu() -> None:
    items = [
        ("1", "Compose a log message (pick level/folder/file)"),
        ("2", "Run the demo (write all levels, print files)"),
        ("3", "Tail / preview a log file"),
        ("4", "Show where logs are written"),
        ("q", "Quit"),
    ]
    if _HAVE_RICH:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(justify="right", style="bold yellow")
        table.add_column()
        for key, label in items:
            table.add_row(key, label)
        _console.print(Panel(table, title="Menu", border_style="yellow",
                             padding=(0, 1)))
    else:
        print(f"\n{_C.YELLOW}Menu{_C.RESET}")
        for key, label in items:
            print(f"  {_C.BOLD}{key}{_C.RESET}) {label}")


# ---------------------------------------------------------------------------
# EOF/pipe-safe input.
# ---------------------------------------------------------------------------
class _Quit(Exception):
    """Raised to unwind out of the interactive loop cleanly on EOF/quit."""


def ask(prompt: str, default: str | None = None,
        choices: list[str] | None = None) -> str:
    """Prompt the user; raise _Quit on EOF or non-TTY stdin."""
    if not sys.stdin.isatty():
        raise _Quit()
    try:
        if _HAVE_RICH:
            return Prompt.ask(prompt, default=default, choices=choices)
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            return default
        return raw
    except (EOFError, KeyboardInterrupt):
        raise _Quit()


# ---------------------------------------------------------------------------
# Real capabilities.
# ---------------------------------------------------------------------------
def tail_file(path: Path, limit: int = 20) -> list[str]:
    """Return the last `limit` lines of a log file (safe if missing)."""
    if not path.exists():
        return []
    with path.open("r", errors="replace") as fh:
        lines = fh.readlines()
    return [ln.rstrip("\n") for ln in lines[-limit:]]


def render_lines(path: Path, lines: list[str]) -> None:
    if not lines:
        failure(f"No content in {path}")
        return
    if _HAVE_RICH:
        body = "\n".join(lines)
        _console.print(Panel(body, title=str(path), border_style="green",
                             padding=(0, 1)))
    else:
        print(f"{_C.GREEN}--- {path} ---{_C.RESET}")
        for ln in lines:
            print(ln)


def action_compose() -> None:
    """(a) Interactive log composer -> Logs.LogsMessages."""
    level = ask("Level", default="INFO", choices=LEVELS)
    level = level.upper()
    if level not in LEVEL_MAP:
        failure(f"Unknown level {level!r}; using WARNING")
        level = "WARNING"
    folder = ask("Folder (blank = main.log fallback)", default="CustomLogs")
    file_name = ask("File name", default="event.log")
    message = ask("Message", default="Composed from the dashboard")

    with Logs() as log:
        if folder and file_name:
            log.LogsMessages(message, message_type=level.lower(),
                             folder_name=folder, file_name=file_name)
            target = Path(log.construct_path(folder, file_name))
        else:
            log.LogsMessages(message, message_type=level.lower())
            target = Path(log.mainloggerfile)
        for h in log.main_logger.handlers:
            h.flush()
        for lg in log._managed_loggers:
            for h in lg.handlers:
                h.flush()
    success(f"Wrote {level} message to {target}")
    render_lines(target, tail_file(target, limit=6))


def _run_demo_writes(base_dir: Path) -> dict[str, Path]:
    """Write sample messages across ALL levels to a couple of files.

    Returns a mapping of label -> file path. Used by both --demo and the
    interactive demo action, so output is identical and honest.
    """
    app_log = base_dir / "app.log"
    audit_log = base_dir / "audit.log"
    main_log = base_dir / "main.log"

    with Logs(main_log_file=str(main_log)) as log:
        # Sample messages across every level to app.log.
        for level in LEVELS:
            log.LogsMessages(
                f"sample {level} message from the demo",
                message_type=level.lower(),
                folder_name=str(base_dir),
                file_name="app.log",
            )
        # A second file demonstrating direct folder/file targeting.
        log.LogsMessages("user login recorded", message_type="info",
                         folder_name=str(base_dir), file_name="audit.log")
        log.LogsMessages("permission escalation", message_type="critical",
                         folder_name=str(base_dir), file_name="audit.log")
        # A fallback-to-main-logger write.
        log.LogsMessages("engine heartbeat", message_type="warning")
        for lg in log._managed_loggers:
            for h in lg.handlers:
                h.flush()

    return {"app.log": app_log, "audit.log": audit_log, "main.log": main_log}


def action_demo(interactive: bool = True) -> int:
    """(b) Scripted showcase: write sample logs, then print file contents."""
    banner()
    out()
    tmp = tempfile.mkdtemp(prefix="logger_demo_")
    base = Path(tmp)
    try:
        files = _run_demo_writes(base)
        if _HAVE_RICH:
            summary = Table(show_header=True, header_style="bold cyan", box=None)
            summary.add_column("File")
            summary.add_column("Lines", justify="right")
            summary.add_column("Path", style="dim")
            for label, path in files.items():
                n = len(tail_file(path, limit=10_000))
                summary.add_row(label, str(n), str(path))
            _console.print(Panel(summary, title="Demo wrote", border_style="cyan"))
        else:
            print("Demo wrote:")
            for label, path in files.items():
                n = len(tail_file(path, limit=10_000))
                print(f"  {label}: {n} line(s) -> {path}")
        out()
        for label, path in files.items():
            render_lines(path, tail_file(path, limit=10))
        out()
        success("Demo complete: sample logs written across all levels.")
        return 0
    finally:
        # Clean up temp files.
        for p in base.rglob("*"):
            try:
                p.unlink()
            except OSError:
                pass
        try:
            base.rmdir()
        except OSError:
            pass


def action_tail() -> None:
    """(c) Tail/preview a chosen log file."""
    logs = sorted(PROJECT_DIR.rglob("*.log"))
    if not logs:
        failure("No .log files found yet. Compose one or run the demo first.")
        return
    if _HAVE_RICH:
        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("#", justify="right", style="yellow")
        table.add_column("File")
        for i, p in enumerate(logs, 1):
            table.add_row(str(i), str(p.relative_to(PROJECT_DIR)))
        _console.print(Panel(table, title="Log files", border_style="cyan"))
    else:
        print("Log files:")
        for i, p in enumerate(logs, 1):
            print(f"  {i}) {p.relative_to(PROJECT_DIR)}")
    choice = ask("Pick a file number", default="1")
    try:
        idx = int(choice) - 1
        target = logs[idx]
    except (ValueError, IndexError):
        failure("Invalid selection")
        return
    render_lines(target, tail_file(target, limit=20))


def action_where() -> None:
    """(d) Show where logs are written."""
    with Logs() as log:
        main_path = log.mainloggerfile
        sample_engine = log.construct_path("ExampleLogger", "ExampleLogger.log")
        sample_custom = log.construct_path("CustomLogs", "event.log")
    if _HAVE_RICH:
        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("Kind")
        table.add_column("Resolved path", style="green")
        table.add_row("Main fallback logger", main_path)
        table.add_row("Engine logger (folder/file)", sample_engine)
        table.add_row("Direct-target logger", sample_custom)
        _console.print(Panel(table, title="Where logs go", border_style="cyan"))
    else:
        print("Where logs go:")
        print(f"  Main fallback : {main_path}")
        print(f"  Engine logger : {sample_engine}")
        print(f"  Direct target : {sample_custom}")
    out("Rules: relative paths resolve against the current working dir; a `.log`")
    out("extension is appended if missing; parent directories are created.")


# ---------------------------------------------------------------------------
# Interactive loop.
# ---------------------------------------------------------------------------
def interactive_loop() -> int:
    banner()
    status_panel()
    actions = {
        "1": action_compose,
        "2": lambda: action_demo(interactive=True),
        "3": action_tail,
        "4": action_where,
    }
    try:
        while True:
            menu()
            choice = ask("Choose", default="q")
            choice = (choice or "").strip().lower()
            if choice in ("q", "quit", "exit"):
                break
            fn = actions.get(choice)
            if fn is None:
                failure(f"Unknown option {choice!r}")
                continue
            out()
            try:
                fn()
            except _Quit:
                raise
            except Exception as exc:  # keep the loop resilient
                failure(f"Action failed: {exc}")
            out()
    except _Quit:
        out()
        out("Input stream closed — exiting.")
    except KeyboardInterrupt:
        out()
        out("Interrupted — exiting.")
    out("Goodbye.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dashboard.py",
        description=f"{APP_NAME} — {TAGLINE}",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run a scripted, non-interactive showcase and exit.",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        return action_demo(interactive=False)
    if not sys.stdin.isatty():
        # Non-TTY with no --demo: show a banner + status and exit cleanly
        # instead of blocking on input (EOF/pipe-safe requirement).
        banner()
        status_panel()
        out()
        out("Non-interactive stdin detected. Try: python3 dashboard.py --demo")
        return 0
    return interactive_loop()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
