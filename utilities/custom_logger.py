# utilities/custom_logger.py
"""
Logging utility module.

Provides a helper to obtain a configured named logger with both file
and console handlers. Ensures log files are created under ``logs/``
at the project root, and attaches a single stream handler to stdout.
"""
import logging
import os
import sys

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init()  # enable ANSI on Windows
    _HAS_COLOR = True
except Exception:
    _HAS_COLOR = False


_LEVEL_TO_COLOR = {
    "DEBUG":  "CYAN",
    "INFO":   "GREEN",
    "WARNING":"YELLOW",
    "ERROR":  "RED",
    "CRITICAL":"RED",
}

_COLOR = {
    "CYAN":     "\x1b[36m",
    "GREEN":    "\x1b[32m",
    "YELLOW":   "\x1b[33m",
    "RED":      "\x1b[31m",
    "RESET":    "\x1b[0m",
}


class ColoredAlignedFormatter(logging.Formatter):
    """
    Keeps your exact aligned layout, but colors the LEVEL column in console.
    We pad first, then wrap with ANSI so alignment is preserved.
    """
    def format(self, record: logging.LogRecord) -> str:
        # Precompute padded fields (do NOT color yet or padding gets skewed)
        level_padded = f"{record.levelname:<8}"
        name_padded  = f"{record.name:<20}"
        time_stamp   = f"{record.asctime}"

        # Inject into record for our format string
        record.level_padded = level_padded
        record.name_padded  = name_padded

        s = super().format(record)

        # Color only the level column for console
        if _HAS_COLOR:
            color_level = _LEVEL_TO_COLOR.get(record.levelname, None)
            if color_level:
                s = s.replace(level_padded,f"{_COLOR[color_level]}{level_padded}{_COLOR['RESET']}",
                              1)
        return s


class LogGen:
    """
    Factory for creating preconfigured loggers.

    Usage:
    ```python
    from utilities.custom_logger import LogGen

    logger = LogGen.loggen("ui")
    logger.info("Test started")
    ```
    """

    @staticmethod
    def loggen(name: str = "ui") -> logging.Logger:
        """
        Create or retrieve a named logger with file and console handlers.

        Configuration:
          * **FileHandler** → ``<project_root>/logs/test_<RUN_ID>.log``
            (if ``RUN_ID`` is set in environment), else ``test.log``.
          * **StreamHandler** → console (stdout).
          * Format: ``"%(asctime)s | %(levelname)s | %(name)s | %(message)s"``.

        Idempotency:
          * Multiple calls with the same ``name`` return the same logger.
          * Avoids duplicate file handlers across runs by checking the file path.
          * Ensures only one console handler is attached.

        :param name: Logger name (namespace). Defaults to ``"ui"``.
        :returns: Configured :class:`logging.Logger` instance.
        """
        here = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(here, os.pardir))
        log_dir = os.path.join(project_root, "logs")
        os.makedirs(log_dir, exist_ok=True)

        run_id = os.getenv("RUN_ID")
        file_name = f"test_{run_id}.log" if run_id else "test.log"
        log_file = os.path.join(log_dir, file_name)

        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.propagate = False

        file_formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        console_formatter = ColoredAlignedFormatter(
            fmt="%(asctime)s | %(level_padded)s | %(name_padded)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Remove outdated file handlers (from previous runs/log paths)
        for h in list(logger.handlers):
            if isinstance(h, logging.FileHandler):
                base = getattr(h, "baseFilename", "")
                try:
                    same = os.path.samefile(base, log_file)
                except Exception:
                    same = (os.path.abspath(base) == os.path.abspath(log_file))
                if not same:
                    logger.removeHandler(h)

        # Ensure a single file handler
        have_file = any(isinstance(h, logging.FileHandler) for h in logger.handlers)
        if not have_file:
            fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
            fh.setFormatter(file_formatter)
            logger.addHandler(fh)

        # Ensure a single console handler (exclude FileHandler which subclasses StreamHandler)
        def _is_console_handler(h) -> bool:
            if isinstance(h, logging.FileHandler):
                return False
            if isinstance(h, logging.StreamHandler):
                return getattr(h, "stream", None) in (sys.stdout, sys.stderr)
            return False

        have_console = any(_is_console_handler(h) for h in logger.handlers)
        if not have_console:
            ch = logging.StreamHandler(stream=sys.stdout)
            ch.setFormatter(console_formatter)
            logger.addHandler(ch)

        return logger
