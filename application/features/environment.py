"""
Module: Behave environment hooks for Selenium-based UI tests.
Provides lifecycle hooks to create and dispose the WebDriver, and capture artifacts.
"""
import os
import time
import colorama
from datetime import datetime
from typing import Optional

import allure
from allure_commons.types import AttachmentType

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from commons.types.context_protocols import TestContext
from typing import cast
from behave import fixture, use_fixture

from utilities.data_registry import get_data_file, parse_data_file
from utilities.read_property import ReadConfig
from utilities.custom_logger import LogGen
import sys
from pathlib import Path

# --- ensure project root on sys.path ---
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# --- discover current app dir/name from this file's location ---
APP_DIR = Path(__file__).resolve().parents[1]  # e.g., .../application
APP_NAME = APP_DIR.name

# --- export for other utilities (e.g., locator_registry) ---
os.environ.setdefault("APP_DIR", str(APP_DIR))
os.environ.setdefault("APP_NAME", APP_NAME)

logger = LogGen.loggen('Hooks')


def print_effect(text: str, *effects: str) -> None:
    """
    Print text using ANSI sequences to change colour, effects etc. If no effects are
    mentioned, then the text is printed in default terminal colour.
    :param text: The text to be printed.
    :param effects: The colours or effects that we want to apply on the text based on the
        constants mentioned at the start of the file.
    """
    effect_string = "".join(effects)
    output_string = "{0}{1}{2}".format(effect_string, text, '\u001b[0m')
    print(output_string)


def _ensure_dir(path: str) -> None:
    """
    Ensure that the given directory path exists (create if missing).

    Args:
        path: Absolute or relative directory path.
    Returns:
        None.
    """
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def _select_browser() -> str:
    """
    Select target browser based on configuration (defaults to 'chrome').

    Returns:
        The browser name to use: 'chrome' or 'firefox'.
    """
    try:
        return getattr(ReadConfig, "get_browser", lambda: "chrome")()
    except Exception:
        return "chrome"


def _safe_get_driver(context):
    for attr in ("driver", "web_driver", "browser"):
        if hasattr(context, attr) and getattr(context, attr) is not None:
            return getattr(context, attr)
    return None


def _attach_text(name: str, text: str) -> None:
    try:
        allure.attach(text or "", name=name, attachment_type=AttachmentType.TEXT)
    except Exception:
        pass


def _attach_png(name: str, png_bytes: Optional[bytes]) -> None:
    try:
        if png_bytes:
            allure.attach(png_bytes, name=name, attachment_type=AttachmentType.PNG)
    except Exception:
        pass


def _screenshot_bytes(driver) -> Optional[bytes]:
    try:
        return driver.get_screenshot_as_png()
    except Exception:
        return None


def before_all(context) -> None:
    """
    Behave hook executed once before the whole test run.
    Initializes common directories for reports and downloads.
    """
    ctx = cast(TestContext, context)
    # point project_root to repo root
    ctx.project_root = str(ROOT)

    # make reports/download app-specific
    ctx.reports_dir = os.path.join(ctx.project_root, "reports", APP_NAME)
    ctx.download_dir = os.path.join(ctx.project_root, "download", APP_NAME)

    _ensure_dir(ctx.reports_dir)
    _ensure_dir(ctx.download_dir)

    # expose app info
    ctx.app_dir = str(APP_DIR)
    ctx.app_name = APP_NAME
    ctx.base_url = ReadConfig.get_application_url()
    ctx.data = {}
    try:
        from time import strftime
        context.allure_run_id = strftime("%Y%m%d-%H%M%S")
    except Exception:
        context.allure_run_id = "run"


def before_feature(context, feature) -> None:
    """
    Load the feature level data file once and store it in context.
    :param context: TestContext for the scenario.
    :param feature: feature object containing details of feature filename and feature itself.
    """
    if feature.tags:
        print(" ".join(t if t.startswith("@") else f"@{t}" for t in feature.tags))

        # single-line Feature header with short location, no wrapping
    loc = f"{os.path.basename(feature.filename)}:{feature.line}"
    print_effect(f"Feature: {feature.name}  # {loc}", '\u001b[94m', '\u001b[21m', '\u001b[1m')

    # (optional) track duration
    context._feature_started_at = time.monotonic()
    data_file = get_data_file(feature.filename)
    context.data_file_path = data_file
    context.data_file_content = parse_data_file(data_file)


def before_scenario(context, scenario) -> None:
    """
    Behave hook executed before each scenario.
    Creates the WebDriver and attaches it to the Behave context.

    Args:
        context: Behave context bag.
        scenario: Current scenario object.
    """
    loc = f"{os.path.basename(scenario.filename)}:{scenario.line}"
    print_effect(f"\nScenario: {scenario.name}       # {loc}", '\u001b[92m', '\u001b[1m')
    ctx = cast(TestContext, context)
    browser = _select_browser()
    cli_val = context.config.userdata.get("headless")  # "true"/"false" or None
    if cli_val is not None:
        headless = str(cli_val).strip().lower() in ("1", "true", "yes", "y", "on")
    else:
        from utilities.read_property import ReadConfig
        headless = ReadConfig.get_headless(default=False)

    if browser.lower() == "firefox":
        options = FirefoxOptions()
        options.headless = headless
        options.set_preference("browser.download.folderList", 2)
        options.set_preference("browser.download.dir", context.download_dir)
        options.set_preference("browser.download.useDownloadDir", True)
        options.set_preference(
            "browser.helperApps.neverAsk.saveToDisk",
            "application/pdf,application/octet-stream"
        )
        ctx.driver = webdriver.Firefox(options=options)
    else:
        options = ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--start-maximized")
        options.add_experimental_option("prefs", {
            "download.default_directory": context.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True
        })
        ctx.driver = webdriver.Chrome(options=options)

    ctx.driver.set_page_load_timeout(60)
    setattr(ctx.driver, "_behave_context", context)  # NEW
    logger.info(f"Started {browser} for scenario: {scenario.name}")


def before_step(context, step) -> None:
    loc = f"{os.path.basename(step.filename)}:{step.line}"
    print_effect(f"{step.keyword} {step.name}      #{loc}", '\u001b[3m', '\u001b[1m')


def after_step(context, step) -> None:
    """
    Attach URL and a screenshot for EVERY step (passed/failed/skipped/undefined).
    If failed, also attach page source for deep debugging.
    """
    driver = _safe_get_driver(context)
    status = getattr(step, "status", None)
    status_str = getattr(status, "name", str(status))  # handle Behave Status enum or string
    title = f"{step.keyword} {step.name} [{status_str}]"

    if driver is not None:
        # URL
        try:
            _attach_text("URL", getattr(driver, "current_url", ""))
        except Exception:
            pass

        # Screenshot every step
        _attach_png(f"Screenshot - {title}", _screenshot_bytes(driver))

        # Page source on failures
        if str(status_str).lower() == "failed":
            try:
                _attach_text("Page Source", driver.page_source)
            except Exception:
                pass


def after_scenario(context, scenario) -> None:
    """
    Behave hook executed after each scenario.
    Captures a screenshot on failure and quits the WebDriver.

    Args:
        context: Behave context bag.
        scenario: Current scenario object.
    """

    ctx = cast(TestContext, context)
    driver = _safe_get_driver(context)

    if driver is not None:
        _attach_png(f"Scenario End - {scenario.name}", _screenshot_bytes(driver))

    try:
        status = getattr(scenario, "status", None)
        status_str = getattr(status, "name", str(status))
        if str(status_str).lower() == "failed" and driver is not None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in scenario.name)
            screenshot_path = os.path.join(context.reports_dir, f"{safe}_{ts}.png")
            driver.save_screenshot(screenshot_path)
            logger.info(f"Saved failure screenshot: {screenshot_path}")
    except Exception as e:
        logger.error(f"Failed to capture on-disk screenshot: {e}")

        # Quit like before
    try:
        if driver is not None:
            driver.quit()
        logger.info("WebDriver closed.")
    except Exception:
        pass


def after_feature(context, feature):
    # optional footer; keep it simple or remove if you don't want it
    started = getattr(context, "_feature_started_at", None)
    if started is not None:
        dur = time.monotonic() - started
        print(f"Feature duration: {dur:.2f}s")
    print("#" * 200)  # simple separator


def after_all(context) -> None:
    """
    Behave hook executed once after the whole test run.
    Placeholder for any global teardown.
    """
    logger.info("Test run complete.")
