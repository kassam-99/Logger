import importlib
import logging
import os

import pytest

import Logger
from Logger import Logs, LEVEL_MAP


def test_import_smoke():
    """Module imports and exposes the public API."""
    mod = importlib.reload(Logger)
    assert hasattr(mod, "Logs")
    assert callable(mod.Logs)


def test_resolve_log_path_appends_extension(tmp_path):
    log = Logs(main_log_file=str(tmp_path / "main.log"))
    try:
        p = log.resolve_log_path(str(tmp_path / "foo"))
        assert p.endswith("foo.log")
        assert os.path.isabs(p)
    finally:
        log.close()


def test_resolve_log_path_no_double_extension(tmp_path):
    log = Logs(main_log_file=str(tmp_path / "main.log"))
    try:
        p = log.resolve_log_path(str(tmp_path / "foo.log"))
        assert p.endswith("foo.log")
        assert not p.endswith("foo.log.log")
    finally:
        log.close()


def test_construct_path_no_double_extension(tmp_path):
    log = Logs(main_log_file=str(tmp_path / "main.log"))
    try:
        # Passing a name already ending in .log must not double it.
        p = log.construct_path(str(tmp_path), "Example.log")
        assert p.endswith("Example.log")
        assert not p.endswith("Example.log.log")
    finally:
        log.close()


def test_log_engine_produces_single_extension(tmp_path):
    """Regression test for the double-.log bug in LogEngine."""
    log = Logs(main_log_file=str(tmp_path / "main.log"))
    try:
        folder = str(tmp_path / "Engine")
        log.LogEngine(folder, "MyEngine.log")
        log.LogsMessages("hi", message_type="info")
        expected = os.path.join(folder, "MyEngine.log")
        assert os.path.exists(expected)
        assert not os.path.exists(expected + ".log")
    finally:
        log.close()


def test_level_map_covers_all_levels():
    assert set(LEVEL_MAP) == {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    assert LEVEL_MAP["ERROR"] == logging.ERROR


def test_log_to_file_unknown_level_defaults_warning(tmp_path):
    log = Logs(main_log_file=str(tmp_path / "main.log"))
    try:
        # Should not raise on an unknown level.
        log.log_to_file("msg", "BOGUS")
    finally:
        log.close()


def test_fallback_to_main_logger_writes(tmp_path):
    main_file = tmp_path / "main.log"
    log = Logs(main_log_file=str(main_file))
    try:
        # No engine and no folder/file -> falls back to main logger.
        log.LogsMessages("fallback message", message_type="error")
        for h in log.main_logger.handlers:
            h.flush()
        assert main_file.exists()
        assert "fallback message" in main_file.read_text()
    finally:
        log.close()


def test_direct_folder_file_targeting(tmp_path):
    log = Logs(main_log_file=str(tmp_path / "main.log"))
    try:
        folder = str(tmp_path / "Custom")
        log.LogsMessages("direct", message_type="info",
                         folder_name=folder, file_name="event.log")
        target = os.path.join(folder, "event.log")
        assert os.path.exists(target)
    finally:
        log.close()


def test_context_manager_closes_handlers(tmp_path):
    with Logs(main_log_file=str(tmp_path / "main.log")) as log:
        log.LogEngine(str(tmp_path / "E"), "eng")
        managed = list(log._managed_loggers)
    # After close, managed loggers have no file handlers left.
    for lg in managed:
        assert not any(isinstance(h, logging.FileHandler) for h in lg.handlers)


def test_empty_dirname_does_not_crash(tmp_path, monkeypatch):
    # Bare filename (no directory component) must not raise FileNotFoundError.
    monkeypatch.chdir(tmp_path)
    log = Logs(main_log_file=str(tmp_path / "main.log"))
    try:
        p = log.construct_path("", "bare")
        assert p.endswith("bare.log")
    finally:
        log.close()


def test_rotation_uses_rotating_handler(tmp_path):
    import logging.handlers
    log = Logs(main_log_file=str(tmp_path / "main.log"), use_rotation=True,
               max_bytes=100, backup_count=1)
    try:
        assert any(isinstance(h, logging.handlers.RotatingFileHandler)
                   for h in log.main_logger.handlers)
    finally:
        log.close()


def test_file_output_strips_ansi(tmp_path):
    """Colorized messages must be written to files as clean, escape-free text."""
    main_file = tmp_path / "main.log"
    log = Logs(main_log_file=str(main_file))
    try:
        log.LogsMessages("\x1b[31mred alert\x1b[0m", message_type="error")
        for h in log.main_logger.handlers:
            h.flush()
        contents = main_file.read_text()
        assert "red alert" in contents
        assert "\x1b[" not in contents  # no raw ANSI escape sequences in the file
    finally:
        log.close()


def test_cli_main_writes_message(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = Logger.main(["--message", "cli hello", "--level", "INFO",
                      "--folder", str(tmp_path / "cli"), "--file", "out.log"])
    assert rc == 0
    target = os.path.join(str(tmp_path / "cli"), "out.log")
    assert os.path.exists(target)
    assert "cli hello" in open(target).read()
