# utilities/read_property.py
"""
Configuration accessor for the Selenium BDD project.

Wraps reading from ``configuration/config.ini`` with simple static helpers.
All methods on ``ReadConfig`` are safe to call from steps or utilities.
"""
from __future__ import annotations

import configparser
import os



# Resolve the config.ini path relative to this file:
#   utilities/read_property.py → ../configuration/config.ini
_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "configuration",
    "config.ini",
)
_CONFIG = configparser.ConfigParser()
_CONFIG.read(_CONFIG_PATH)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class ReadConfig:
    """
    Static helpers to fetch configuration values from ``config.ini``.

    Expected sections/keys (typical):
      - ``[environment] type = qa`` (or ``dev``, ``stage``, etc.)
      - ``[common_info] qa_baseURL = https://...``
      - ``[common_info] qa_userName = user``
      - ``[common_info] qa_password = pass``
      - ``[wait] sec10 = 10``
      - ``[wait] sec5 = 5``
      - (optional) ``[driver configuration] browser = chrome``
    """

    @staticmethod
    def get_env(default: str = "qa") -> str:
        """
        Get active environment key (e.g., ``'qa'``, ``'dev'``).

        :param default: Fallback environment if the key is missing.
        :returns: Environment name as a string.
        """
        try:
            return _CONFIG.get("environment", "type")
        except Exception:
            return default

    @staticmethod
    def get_application_url() -> str:
        """
        Get the application base URL for the active environment.

        Looks up ``[common_info] <env>_baseURL``.

        :returns: Base URL string (e.g., ``'https://www.saucedemo.com/'``).
        :raises KeyError/NoOptionError: If the key is missing in ``config.ini``.
        """
        env = ReadConfig.get_env()
        return _CONFIG.get("common_info", f"{env}_baseURL")

    @staticmethod
    def get_application_user_name() -> str:
        """
        Get the username for the active environment.

        Looks up ``[common_info] <env>_userName``.

        :returns: Username string.
        :raises KeyError/NoOptionError: If the key is missing in ``config.ini``.
        """
        env = ReadConfig.get_env()
        return _CONFIG.get("common_info", f"{env}_userName")

    @staticmethod
    def get_application_password() -> str:
        """
        Get the password for the active environment.

        Looks up ``[common_info] <env>_password``.

        :returns: Password string.
        :raises KeyError/NoOptionError: If the key is missing in ``config.ini``.
        """
        env = ReadConfig.get_env()
        return _CONFIG.get("common_info", f"{env}_password")

    @staticmethod
    def get_wait_time_10_sec() -> int:
        """
        Get a standard explicit wait time of 10 seconds.

        Reads ``[wait] sec10``.

        :returns: Integer seconds for the 10s wait.
        :raises ValueError/NoOptionError: If the value is missing or not an int.
        """
        return int(_CONFIG.get("wait", "sec10"))

    @staticmethod
    def get_wait_time_5_sec() -> int:
        """
        Get a standard explicit wait time of 5 seconds.

        Reads ``[wait] sec5``.

        :returns: Integer seconds for the 5s wait.
        :raises ValueError/NoOptionError: If the value is missing or not an int.
        """
        return int(_CONFIG.get("wait", "sec5"))

    @staticmethod
    def get_browser(default: str = "chrome") -> str:
        """
        (Optional) Get the target browser name from config, if present.

        Reads ``[driver configuration] browser``. Falls back to ``default`` if not set.

        :param default: Fallback browser name (e.g., ``'chrome'`` or ``'firefox'``).
        :returns: Browser name string.
        """
        try:
            return _CONFIG.get("driver configuration", "browser")
        except Exception:
            return default

    @staticmethod
    def get_headless(default: bool = False) -> bool:
        """
        Return the headless flag from [driver configuration] section in config.ini.
        :param default: Fallback if value not present or parse fails.
        """
        try:
            import configparser
            cfg_path = ROOT / "configuration" / "config.ini"
            cp = configparser.ConfigParser()
            cp.read(cfg_path)
            val = cp.get("driver configuration", "headless", fallback=str(default))
            return str(val).strip().lower() in ("1", "true", "yes", "y", "on")
        except Exception:
            return default