import argparse
import logging
import logging.handlers
import os
import re
from typing import Optional

# Known logging levels, used for validation and CLI choices.
LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

# Matches CSI SGR sequences like "\x1b[31m" / "\x1b[0m" used for terminal colors.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Remove ANSI color/style escape codes from a string."""
    return _ANSI_RE.sub("", text)


class AnsiStrippingFormatter(logging.Formatter):
    """Formatter that strips ANSI codes so log FILES stay clean plain text.

    Callers (e.g. ``print_and_log``) may pass colorized messages meant for the
    console; the console keeps its colors while the file sink records readable,
    grep-friendly text with no escape sequences.
    """

    def format(self, record: logging.LogRecord) -> str:
        return strip_ansi(super().format(record))


class Logs:

    def __init__(
        self,
        default_log_level: int = logging.DEBUG,
        main_log_file: str = "main.log",
        use_rotation: bool = False,
        max_bytes: int = 1_048_576,
        backup_count: int = 3,
    ):
        self.default_log_level = default_log_level
        self.log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        self.use_rotation = use_rotation
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.mainloggerfile = self.resolve_log_path(main_log_file)
        self.logger = None
        # Track every logger we manage so close() can release file handles.
        self._managed_loggers = set()

        # Initialize the main logger
        self.main_logger = logging.getLogger("MainLogger")
        self.main_logger.setLevel(self.default_log_level)
        self.main_logger.propagate = False  # Prevent logging from printing to terminal

        # Drop any existing handlers (closing FileHandlers to avoid fd leaks).
        self._clear_handlers(self.main_logger)

        main_handler = self._make_handler(self.mainloggerfile)
        main_handler.setFormatter(AnsiStrippingFormatter(self.log_format))
        main_handler.setLevel(self.default_log_level)
        self.main_logger.addHandler(main_handler)
        self._managed_loggers.add(self.main_logger)

    def _make_handler(self, path: str) -> logging.Handler:
        """Create a FileHandler (or RotatingFileHandler when rotation is enabled).

        ``delay=True`` defers opening the file until the first record is
        emitted, so merely constructing ``Logs`` never touches the filesystem
        (avoids stray/permission-denied files, e.g. after a read-only install).
        """
        if self.use_rotation:
            return logging.handlers.RotatingFileHandler(
                path, maxBytes=self.max_bytes, backupCount=self.backup_count,
                delay=True,
            )
        return logging.FileHandler(path, delay=True)

    @staticmethod
    def _clear_handlers(logger: logging.Logger) -> None:
        """Remove all handlers from a logger, closing FileHandlers to release fds."""
        for handler in list(logger.handlers):
            if isinstance(handler, logging.FileHandler):
                handler.close()
            logger.removeHandler(handler)

    def resolve_log_path(self, path: str) -> str:
        """Resolve relative or absolute path to absolute, ensuring it ends with `.log`."""
        if not path.lower().endswith(".log"):
            path += ".log"

        if not os.path.isabs(path):
            # Resolve against the current working directory, NOT the module
            # install dir, so logs land where the app runs instead of inside
            # site-packages (which is often read-only after `pip install`).
            path = os.path.join(os.getcwd(), path)

        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        return os.path.abspath(path)

    def construct_path(self, folder_name: str, file_name: str) -> str:
        """Construct full path from folder and file, respecting relative or absolute paths."""
        if not file_name.lower().endswith(".log"):
            file_name += ".log"

        if os.path.isabs(folder_name):
            full_path = os.path.join(folder_name, file_name)
        else:
            # Resolve relative folders against the current working directory,
            # NOT the module install dir (see resolve_log_path).
            base_dir = os.getcwd()
            full_path = os.path.join(base_dir, folder_name, file_name)

        directory = os.path.dirname(full_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        return os.path.abspath(full_path)

    def log_to_file(self, message: str, TypeLog: str) -> None:
        level = TypeLog.upper()
        if level not in LEVEL_MAP:
            logging.getLogger("MainLogger").warning(
                "Unknown log level %r; defaulting to WARNING", TypeLog
            )
        log_level = LEVEL_MAP.get(level, logging.WARNING)
        self.main_logger.log(log_level, message)

    def LogEngine(self, folder_name: str, log_name: str) -> None:
        """Set up a named logger and resolve the file path correctly."""
        # Let construct_path normalize the `.log` extension (avoids double `.log`).
        full_path = self.construct_path(folder_name, log_name)

        self.logger = logging.getLogger(log_name)
        self.logger.setLevel(self.default_log_level)
        self.logger.propagate = False  # Prevent printing to terminal

        # Clear existing FileHandlers, closing them first to avoid fd leaks.
        for handler in self.logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                handler.close()
                self.logger.removeHandler(handler)

        handler = self._make_handler(full_path)
        handler.setFormatter(AnsiStrippingFormatter(self.log_format))
        handler.setLevel(self.default_log_level)
        self.logger.addHandler(handler)
        self._managed_loggers.add(self.logger)

    def LogsMessages(
        self,
        message: str,
        message_type: str = "info",
        folder_name: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> None:
        if message_type.upper() not in LEVEL_MAP:
            logging.getLogger("MainLogger").warning(
                "Unknown message_type %r; defaulting to WARNING", message_type
            )

        if folder_name and file_name:
            full_path = self.construct_path(folder_name, file_name)

            temp_logger = logging.getLogger(f"{folder_name}_{file_name}")
            temp_logger.setLevel(self.default_log_level)
            temp_logger.propagate = False  # Prevent printing to terminal

            if not any(isinstance(h, logging.FileHandler) and h.baseFilename == full_path
                       for h in temp_logger.handlers):
                handler = self._make_handler(full_path)
                handler.setFormatter(AnsiStrippingFormatter(self.log_format))
                temp_logger.addHandler(handler)
                self._managed_loggers.add(temp_logger)

            getattr(temp_logger, message_type.lower(), temp_logger.warning)(message)
        elif self.logger:
            log_method = getattr(self.logger, message_type.lower(), self.logger.warning)
            log_method(message)
        else:
            self.log_to_file(message, message_type.upper())

    def print_and_log(
        self,
        message: str,
        message_type: str = "info",
        folder_name: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> None:
        self.LogsMessages(message, message_type, folder_name, file_name)
        print(message)

    def close(self) -> None:
        """Close and remove all handlers on every managed logger, releasing file descriptors."""
        for logger in self._managed_loggers:
            self._clear_handlers(logger)
        self._managed_loggers.clear()
        self.logger = None

    def __enter__(self) -> "Logs":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write a leveled message to a log file using the Logs helper."
    )
    parser.add_argument("--message", "-m", required=True, help="The message to log.")
    parser.add_argument(
        "--level",
        "-l",
        default="INFO",
        choices=sorted(LEVEL_MAP.keys()),
        help="Log level (default: INFO).",
    )
    parser.add_argument("--folder", "-d", default=None, help="Target log folder.")
    parser.add_argument("--file", "-f", default=None, help="Target log file name.")
    parser.add_argument(
        "--print",
        action="store_true",
        help="Also echo the message to stdout.",
    )
    return parser


def main(argv=None) -> int:
    args = _build_arg_parser().parse_args(argv)
    with Logs() as logger:
        if args.print:
            logger.print_and_log(
                args.message,
                message_type=args.level.lower(),
                folder_name=args.folder,
                file_name=args.file,
            )
        else:
            logger.LogsMessages(
                args.message,
                message_type=args.level.lower(),
                folder_name=args.folder,
                file_name=args.file,
            )
    return 0


# ==============================
# Usage Example
# ==============================
if __name__ == "__main__":
    import sys

    # If CLI args are supplied, act as an argparse-driven command-line logger.
    if len(sys.argv) > 1:
        raise SystemExit(main())

    # Otherwise run the original demo.
    with Logs() as logger:
        logger.LogEngine("ExampleLogger", "ExampleLogger")
        logger.LogsMessages("This is a hidden message")
        logger.print_and_log("This is a test message.", message_type="info")

        # You can also directly specify folder and file for a log message
        logger.print_and_log(
            "Direct log to folder",
            message_type="info",
            folder_name="CustomLogs",
            file_name="event.log",
        )
