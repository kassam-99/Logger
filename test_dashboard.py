"""Tests for the CLI dashboard front-end (dashboard.py)."""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
DASH = os.path.join(HERE, "dashboard.py")


def test_demo_runs_and_exits_zero():
    """`dashboard.py --demo` runs the real features and exits 0 quickly."""
    proc = subprocess.run(
        [PY, DASH, "--demo"],
        cwd=HERE,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Demo complete" in proc.stdout
    assert "Traceback" not in proc.stderr


def test_eof_stdin_exits_promptly():
    """Piping /dev/null must exit fast with bounded output (no infinite loop)."""
    start = time.time()
    proc = subprocess.run(
        [PY, DASH],
        cwd=HERE,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=12,
    )
    elapsed = time.time() - start
    assert proc.returncode == 0, proc.stderr
    assert elapsed < 12
    # Output must be bounded (well under 1 MB).
    assert len(proc.stdout) < 1_000_000


def test_help_exits_zero():
    proc = subprocess.run(
        [PY, DASH, "--help"],
        cwd=HERE,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0
    assert "--demo" in proc.stdout
