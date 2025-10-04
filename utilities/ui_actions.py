# utilities/ui_actions.py
from __future__ import annotations
from typing import Optional, List, Tuple, Literal, Any, Dict
from urllib.parse import urlparse, urljoin

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common import TimeoutException, NoSuchElementException

from utilities.locator_registry import locate, candidates, page_url, get_page_url_spec
from utilities.custom_logger import LogGen

# Optional configurable waits; fall back to sane defaults if config is absent.
try:
    from utilities.read_property import ReadConfig

    SEC10 = getattr(ReadConfig, "get_wait_time_10_sec", lambda: 10)()
    SEC5 = getattr(ReadConfig, "get_wait_time_5_sec", lambda: 5)()
except Exception:
    SEC10, SEC5 = 10, 5

logger = LogGen.loggen("UiActions")

ByTuple = Tuple[str, str]


def _normalize_text(s: str) -> str:
    return "".join((s or "").split()).strip()


class UiActions:
    """
    Unified keyed API for UI interactions.

    Each element is addressed by a `(page: str, name: str, **params)` key and
    resolved via the locator registry, which returns an ordered list of locator
    candidates that are tried in sequence with the requested wait strategy.
    """

    sec10: int = SEC10
    sec5: int = SEC5

    def __init__(self, driver: WebDriver, default_timeout: Optional[int] = None) -> None:
        """
        Initialize the UiActions wrapper with a WebDriver and default timeout.

        :param driver: Selenium WebDriver instance.
        :param default_timeout: Default timeout (seconds) used by methods that accept a
                                `timeout` override. Falls back to `UiActions.sec10` if None.
        """
        self.driver = driver
        self.default_timeout = default_timeout or self.sec10

    # -----------------------
    # Page lifecycle / nav
    # -----------------------
    def verify_page_loaded(self) -> None:
        """
        Wait until the page's `document.readyState` is `"complete"`.

        :raises TimeoutException: If the page does not finish loading within the default timeout.
        """
        WebDriverWait(self.driver, self.sec10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

    def open_url(self, url: str) -> "UiActions":
        """
        Open the given URL and wait for the page to fully load.

        :param url: Absolute URL to navigate to.
        :returns: Self for fluent chaining.
        """
        logger.info(f"Open URL: {url}")
        self.driver.get(url)
        self.verify_page_loaded()
        return self

    def open_page(self, page: str, *, timeout: Optional[int] = None, wait_for: str = "load") -> "UiActions":
        """
        Navigate to the URL configured for `page` via the locator registry's `page_url(page)`.

        Behavior:
          - Retrieves the URL from the page YAML using `locator_registry.page_url(page)`.
          - If the URL is relative (no scheme/host) and this UiActions instance has `base_url`
            set (e.g., in your test setup), it will join them with `urljoin`.
          - Navigates with WebDriver.get().
          - Optionally waits for the document ready state to be 'complete' (when wait_for="load").

        :param page: Page name (top-level key) from the page YAML (case-sensitive).
        :param timeout: Max seconds to wait for page load; defaults to the instance's timeout.
        :param wait_for: One of {"load", "none"}; when "load" (default), waits for document.readyState == "complete".
        :returns: Self for fluent chaining.
        :raises AssertionError: If page_url is missing or a relative URL is provided without a `base_url`.
        """

        url_from_yaml = page_url(page)
        if not url_from_yaml:
            raise AssertionError(f"No page_url configured in YAML for page {page!r}.")

        parsed = urlparse(url_from_yaml)
        if not parsed.scheme or not parsed.netloc:
            # Relative URL → require a base_url on this UiActions instance
            base = getattr(self, "base_url", None)
            if not base:
                raise AssertionError(
                    f"page_url for {page!r} appears to be relative ({url_from_yaml!r}) and no UiActions.base_url is set."
                )
            final_url = urljoin(base, url_from_yaml)
        else:
            final_url = url_from_yaml

        to = timeout or getattr(self, "default_timeout", 10)
        self.driver.get(final_url)

        if wait_for.lower() == "load":
            WebDriverWait(self.driver, to).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        logger.info(f"{page} page loaded successfully.")

        return self

    def navigate_to(self, url: str) -> "UiActions":
        """
        Alias for :meth:`open_url`; navigates to the given URL.

        :param url: Absolute URL to navigate to.
        :returns: Self for fluent chaining.
        """
        return self.open_url(url)

    def navigate_back(self) -> "UiActions":
        """
        Navigate back in the browser history, then wait for page load.

        :returns: Self for fluent chaining.
        """
        logger.info("Navigate: back")
        self.driver.back()
        self.verify_page_loaded()
        return self

    def navigate_forward(self) -> "UiActions":
        """
        Navigate forward in the browser history, then wait for page load.

        :returns: Self for fluent chaining.
        """
        logger.info("Navigate: forward")
        self.driver.forward()
        self.verify_page_loaded()
        return self

    def navigate_refresh(self) -> "UiActions":
        """
        Refresh the current page, then wait for page load.

        :returns: Self for fluent chaining.
        """
        logger.info("Navigate: refresh")
        self.driver.refresh()
        self.verify_page_loaded()
        return self

    # Short aliases sometimes used in steps
    def back(self) -> "UiActions":
        """
        Alias for :meth:`navigate_back`.

        :returns: Self for fluent chaining.
        """
        return self.navigate_back()

    def forward(self) -> "UiActions":
        """
        Alias for :meth:`navigate_forward`.

        :returns: Self for fluent chaining.
        """
        return self.navigate_forward()

    def get_page_title(self) -> str:
        """
        Return the current page title.

        :returns: The current page title as a string.
        """
        title = self.driver.title
        logger.info(f"Page title: {title!r}")
        return title

    # -----------------------
    # Keyed waits / finds
    # -----------------------
    def wait_for_element_present(
            self, page: str, name: str, timeout: Optional[int] = None, **params
    ) -> "UiActions":
        """
        Wait for the element to be **present in the DOM** (not necessarily visible).

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param timeout: Override timeout (seconds) for this call; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: Self for fluent chaining.
        :raises TimeoutException: If the element is not present within the timeout.
        """
        to = timeout or self.default_timeout
        locate(self.driver, page, name, wait="present", timeout=to, **params)
        return self

    def wait_for_element_visible(
            self, page: str, name: str, timeout: Optional[int] = None, **params
    ) -> "UiActions":
        """
        Wait for the element to be **visible**.

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param timeout: Override timeout (seconds) for this call; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: Self for fluent chaining.
        :raises TimeoutException: If the element is not visible within the timeout.
        """
        to = timeout or self.default_timeout
        locate(self.driver, page, name, wait="visible", timeout=to, **params)
        return self

    def wait_for_element_clickable(
            self, page: str, name: str, timeout: Optional[int] = None, **params
    ) -> "UiActions":
        """
        Wait for the element to be **clickable in the DOM** (not necessarily visible).

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param timeout: Override timeout (seconds) for this call; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: Self for fluent chaining.
        :raises TimeoutException: If the element is not present within the timeout.
        """
        to = timeout or self.default_timeout
        locate(self.driver, page, name, wait="clickable", timeout=to, **params)
        return self

    def wait_for_element_invisible(self, page, name, timeout=10, **params):
        """
        Polls until the element is either not present or not displayed.
        Works even when a previous step never switched frames (e.g., modal overlays).
        """
        deadline = time.time() + timeout
        last_exc = None
        while time.time() < deadline:
            try:
                # reuse your existing wait/find; short timeout to poll quickly
                el = self.find_element(page=page, name=name, wait="present", timeout=1, **params)
                if not el.is_displayed():
                    return True
            except TimeoutException as e:
                # not present => it's gone
                return True
            time.sleep(0.2)
        raise TimeoutException(f'Timed out waiting for "{page}.{name}" to disappear') from last_exc

    def find_element(
            self, page: str, name: str, *, wait: str = "present", poll_frequency: float = 0.0,
            timeout: Optional[int] = None, **params) -> WebElement:
        """
        Resolve `(page, name, **params)` and return a single WebElement using the chosen `wait` strategy.

        :param poll_frequency: Frequency of check for fluent wait.
        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param wait: One of {"present", "visible", "clickable"}; controls the wait strategy.
        :param timeout: Override timeout (seconds) for this call; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: The first matching WebElement.
        :raises TimeoutException: If the expected condition is not met within the timeout.
        :raises NoSuchElementException: If the element cannot be located.
        """
        to = timeout or self.default_timeout
        el = locate(self.driver, page, name, wait=wait,poll_frequency=poll_frequency, timeout=to,
        **params)
        return el

    def find_all_elements(
            self, page: str, name: str, *, timeout: Optional[int] = None, **params
    ) -> List[WebElement]:
        """
        Return **all** matching elements for `(page, name, **params)` using locator candidates.

        The method tries each candidate returned by the locator registry and returns the first
        non-empty list of elements found via `presence_of_all_elements_located`.

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param timeout: Override timeout (seconds) for this call; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: A list of matching WebElements (possibly empty if last candidate yields none
                  before timeout, in which case a TimeoutException is raised).
        :raises TimeoutException: If no elements are found within the timeout for all candidates.
        """
        cand_list: List[ByTuple] = candidates(page, name, **params)
        to = timeout or self.default_timeout
        last_exc: Optional[Exception] = None

        for idx, pair in enumerate(cand_list, 1):
            by, sel = pair
            logger.info(f"[{page}.{name}] try {idx}/{len(cand_list)}: {by} -> {sel}")
            try:
                elems: List[WebElement] = WebDriverWait(self.driver, to).until(
                    EC.presence_of_all_elements_located(pair)
                )
                if elems:
                    logger.info(f"[{page}.{name}] matched with {by} -> {sel} (count={len(elems)})")
                    return elems
            except Exception as e:
                last_exc = e
                logger.warning(f"[{page}.{name}] no elements with {by} -> {sel} within {to}s; next...")
        raise TimeoutException(f"No elements found for {page}.{name}") from last_exc

    # ---------------
    # Element actions
    # ---------------
    def click(self, page: str, name: str, *, timeout: Optional[int] = None, **params) -> "UiActions":
        """
        Click the element resolved by `(page, name, **params)` (waits for **clickable**).

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param timeout: Override timeout (seconds) for this call; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: Self for fluent chaining.
        :raises NoSuchElementException: If the element cannot be located.
        :raises TimeoutException: If the element is not clickable within the timeout.
        """
        to = timeout or self.default_timeout
        el= locate(self.driver, page, name, wait="clickable", timeout=to, **params)
        logger.info(f"Click: {page}.{name}({params})")
        el.click()
        return self

    def click_js_element(
            self, page: str, name: str, *, timeout: Optional[int] = None, **params
    ) -> "UiActions":
        """
        Click the element via JavaScript (useful for overlays or stubborn elements).

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param timeout: Override timeout (seconds) for this call; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: Self for fluent chaining.
        :raises NoSuchElementException: If the element cannot be located.
        :raises TimeoutException: If the element is not visible within the timeout.
        """
        to = timeout or self.default_timeout
        el = self.find_element(page, name, wait="visible", timeout=to, **params)
        logger.info(f"Click via JS: {page}.{name}({params})")
        self.driver.execute_script("arguments[0].click()", el)
        return self

    def double_click_the_element(
            self, page: str, name: str, *, timeout: Optional[int] = None, **params
    ) -> "UiActions":
        """
        Perform a **double-click** on the element.

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param timeout: Override timeout (seconds) for this call; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: Self for fluent chaining.
        :raises NoSuchElementException: If the element cannot be located.
        :raises TimeoutException: If the element is not visible within the timeout.
        """
        to = timeout or self.default_timeout
        el = self.find_element(page, name, wait="visible", timeout=to, **params)
        logger.info(f"Double-click: {page}.{name}({params})")
        ActionChains(self.driver).move_to_element(el).double_click().perform()
        return self

    def type_text(self, page: str, name: str, text: str, *, clear: bool = True,
                  timeout: Optional[int] = None, **params, ) -> "UiActions":
        """
        Clear (optionally) and type the provided text into the element.

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param text: String value to type into the element.
        :param clear: If True (default), clears the input before typing.
        :param timeout: Override timeout (seconds) for this call; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: Self for fluent chaining.
        :raises NoSuchElementException: If the element cannot be located.
        :raises TimeoutException: If the element is not visible within the timeout.
        """
        to = timeout or self.default_timeout
        el = self.find_element(page, name, wait="visible", timeout=to, **params)
        logger.info(f"Type into {page}.{name}({params}): {text!r} (clear={clear})")
        if clear:
            el.clear()
        el.send_keys(text)
        return self

    def get_text(self, page: str, name: str, *, wait: str = "visible",
                 poll_frequency: float= 0.0, timeout: Optional[int] = None, **params) -> str:
        """
        Return the text content of the element located by (page, name).

        Notes:
          - Uses the locator registry to resolve (page, name) into one or more candidate locators.
            Candidates are tried in order until one succeeds under the selected wait condition.
          - `wait` controls the expected condition applied per candidate:
              * "present"   -> element exists in the DOM (may be hidden)
              * "visible"   -> element is present and displayed (default)
              * "clickable" -> element is visible and enabled for click
          - `timeout` applies **per candidate**. If multiple candidates are configured, total time
            may be a multiple of `timeout`.

        :param poll_frequency: Frequency of check for fluent wait.
        :param page: Page name (top-level key) from the locator registry (case-sensitive).
        :param name: Element key under the given page in the locator registry (case-sensitive).
        :param wait: One of {"present", "visible", "clickable"}; defaults to "visible".
        :param timeout: Override timeout (seconds) per candidate; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: The element's text (as exposed by Selenium's WebElement.text).
        :raises NoSuchElementException: If the element cannot be located.
        :raises TimeoutException: If the element cannot be located under the selected wait within the timeout.
        """
        to = timeout or self.default_timeout
        el = self.find_element(page, name, wait=wait, poll_frequency=poll_frequency,
                               timeout=to, **params)
        txt = el.text
        logger.info(f"Get text {page}.{name}({params}) -> {txt!r}")
        return txt

    def get_current_url(self) -> str:
        """
        Return the current browser URL.
        """
        return self.driver.current_url

    def is_element_selected(
            self, page: str, name: str, *, timeout: Optional[int] = None, **params
    ) -> bool:
        """
        Return whether the element is **selected/checked**.

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param timeout: Override timeout (seconds) for this call; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: True if the element is selected, else False.
        :raises NoSuchElementException: If the element cannot be located.
        :raises TimeoutException: If the element is not visible within the timeout.
        """
        to = timeout or self.default_timeout
        el = self.find_element(page, name, wait="visible", timeout=to, **params)
        selected = el.is_selected()
        logger.info(f"Is selected {page}.{name}({params}) -> {selected}")
        return selected

    def unselect_checkbox(
            self, page: str, name: str, *, timeout: Optional[int] = None, **params
    ) -> "UiActions":
        """
        Unselect the checkbox element if it is currently selected.

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param timeout: Override timeout (seconds) for this call; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: Self for fluent chaining.
        :raises NoSuchElementException: If the element cannot be located.
        :raises TimeoutException: If the element is not visible within the timeout.
        """
        to = timeout or self.default_timeout
        el = self.find_element(page, name, wait="visible", timeout=to, **params)
        if el.is_selected():
            logger.info(f"Unselect checkbox {page}.{name}({params})")
            el.click()
        else:
            logger.info(f"Checkbox already unselected: {page}.{name}({params})")
        return self

    def select_checkbox(
            self, page: str, name: str, *, timeout: Optional[int] = None, **params
    ) -> "UiActions":
        """
        Select the checkbox element if it is currently unselected.

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param timeout: Override timeout (seconds) for this call; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: Self for fluent chaining.
        :raises NoSuchElementException: If the element cannot be located.
        :raises TimeoutException: If the element is not visible within the timeout.
        """
        to = timeout or self.default_timeout
        el = self.find_element(page, name, wait="visible", timeout=to, **params)
        if not el.is_selected():
            logger.info(f"Selected checkbox {page}.{name}({params})")
            el.click()
        else:
            logger.info(f"Checkbox already selected: {page}.{name}({params})")
        return self

    def select_by_visible_text(
            self, page: str, name: str, text: str, *,
            timeout: Optional[int] = None, **params
    ) -> "UiActions":
        """
        Select an option in a native <select> by its visible text.

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param text: Visible text of the option to select.
        :param timeout: Override timeout (seconds) for element resolution; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for selector interpolation.
        :returns: Self for fluent chaining.
        :raises NoSuchElementException: If the <select>/option cannot be located.
        :raises TimeoutException: If the element is not present/visible within the timeout.
        """
        to = timeout or self.default_timeout
        el = self.find_element(page, name, wait="visible", timeout=to, **params)
        Select(el).select_by_visible_text(text)
        return self

    def select_by_value(
            self, page: str, name: str, value: str, *,
            timeout: Optional[int] = None, **params
    ) -> "UiActions":
        """
        Select an option in a native <select> by its value attribute.

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param value: Option value attribute to select.
        :param timeout: Override timeout (seconds) for element resolution; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for selector interpolation.
        :returns: Self for fluent chaining.
        :raises NoSuchElementException: If the <select>/option cannot be located.
        :raises TimeoutException: If the element is not present/visible within the timeout.
        """
        to = timeout or self.default_timeout
        el = self.find_element(page, name, wait="visible", timeout=to, **params)
        Select(el).select_by_value(value)
        return self

    def select_by_index(
            self, page: str, name: str, index: int, *,
            timeout: Optional[int] = None, **params
    ) -> "UiActions":
        """
        Select an option in a native <select> by its 0-based index.

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param index: Zero-based index of the option to select.
        :param timeout: Override timeout (seconds) for element resolution; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for selector interpolation.
        :returns: Self for fluent chaining.
        :raises NoSuchElementException: If the <select>/option cannot be located.
        :raises TimeoutException: If the element is not present/visible within the timeout.
        """
        to = timeout or self.default_timeout
        el = self.find_element(page, name, wait="visible", timeout=to, **params)
        Select(el).select_by_index(index)
        return self

    def pick_from_custom_dropdown(
            self,
            opener_page: str, opener_name: str,
            option_text: str,
            *,
            menu_page: Optional[str] = None,
            menu_name: Optional[str] = None,
            option_xpath_template: str = ".//*[self::li or self::div][normalize-space()={q}]",
            timeout: Optional[int] = None,
            **params
    ) -> "UiActions":
        """
        Open a custom (non-<select>) dropdown and choose an option by visible text.

        :param opener_page: Page name for the control that opens the dropdown.
        :param opener_name: Element key for the control that opens the dropdown.
        :param option_text: Visible text to pick (exact match).
        :param menu_page: Optional page name for the dropdown menu container (if rendered elsewhere/portal).
        :param menu_name: Optional element key for the dropdown menu container.
        :param option_xpath_template: XPath (relative to the menu container if provided) used to locate options.
                                      Must include `{q}` placeholder which will be replaced by a quoted text literal.
        :param timeout: Override timeout (seconds); defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for selector interpolation.
        :returns: Self for fluent chaining.
        :raises TimeoutException: If opener/menu/option is not found in time.
        :raises NoSuchElementException: If the option node cannot be clicked.
        """
        to = timeout or self.default_timeout

        # 1) Open the dropdown
        self.scroll_to_element(opener_page, opener_name, timeout=to)
        opener = self.find_element(opener_page, opener_name, wait="clickable", timeout=to,
                                   **params)
        opener.click()
        logger.info(f"Expanded dropdown {opener_name} on {opener_page} page.")

        # 2) If a menu container locator is provided (for portals/popovers), wait for it
        menu_scope = None
        if menu_page and menu_name:
            menu_scope = self.find_element(menu_page, menu_name, wait="visible", timeout=to,
                                           **params)
            logger.info(f"Parsing through the {menu_name} dropdown menu. . .")

        # 3) Locate the desired option (within menu scope if provided, else global)
        # Build a quoted literal for XPath safely
        q = f"'{option_text}'" if "'" not in option_text else f'"{option_text}"'
        xpath = option_xpath_template.format(q=q)

        scope = menu_scope if menu_scope is not None else self.driver
        option_el = WebDriverWait(scope, to).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'})", option_el)

        option_el.click()
        logger.info(f"{option_text} option selected from the {menu_name} dropdown menu.")
        return self

    # -----------------------
    # Scrolling / highlighting
    # -----------------------
    def highlight_element(
            self, page: str, name: str, color: str = "red", *, timeout: Optional[int] = None, **params
    ) -> "UiActions":
        """
        Temporarily highlight the element with a colored outline (debug helper).

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param color: CSS color for the temporary outline (e.g., `"yellow"` or `"#ff0"`).
        :param timeout: Override timeout (seconds) for element resolution; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: Self for fluent chaining.
        :raises NoSuchElementException: If the element cannot be located.
        :raises TimeoutException: If the element is not visible/present within the timeout.
        """
        to = timeout or self.default_timeout
        el = self.find_element(page, name, wait="visible", timeout=to, **params)
        try:
            self.driver.execute_script("arguments[0].style.border='3px solid %s';" % color, el)
        except Exception:
            logger.warning("Could not highlight element (script error).")
        return self

    def scroll_page(self, to: Literal["top", "end"]) -> "UiActions":
        """
        Scroll the page to the top or the end.

        :param to: Where to scroll: `"top"` or `"end"`.
        :returns: Self for fluent chaining.
        """
        if to == "top":
            logger.info("Scroll page -> top")
            self.driver.execute_script("scroll(0, -250);")
        else:
            logger.info("Scroll page -> end")
            self.driver.execute_script("scroll(0, 250);")
        return self

    def scroll_to_top(self) -> "UiActions":
        """
        Scroll to the top of the page.

        :returns: Self for fluent chaining.
        """
        return self.scroll_page("top")

    def scroll_to_end(self) -> "UiActions":
        """
        Scroll to the end/bottom of the page.

        :returns: Self for fluent chaining.
        """
        return self.scroll_page("end")

    def scroll_to_element(
            self, page: str, name: str, *, timeout: Optional[int] = None, **params
    ) -> "UiActions":
        """
        Scroll until the element is in view (via `element.scrollIntoView()`).

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param timeout: Override timeout (seconds) for element resolution; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: Self for fluent chaining.
        :raises NoSuchElementException: If the element cannot be located.
        :raises TimeoutException: If the element is not present/visible within the timeout.
        """
        to = timeout or self.default_timeout
        el = self.find_element(page, name, wait="present", timeout=to, **params)
        logger.info(f"Scroll to element {page}.{name}({params})")
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        return self

    # -----------------------
    # Frames
    # -----------------------
    def switch_to_frame(
            self, page: str, name: str, *, timeout: Optional[int] = None, **params
    ) -> "UiActions":
        """
        Switch the driver's context to the specified **frame** element.

        :param page: Page name (top-level key) from the locator registry.
        :param name: Element key under the given page in the locator registry.
        :param timeout: Override timeout (seconds) for element resolution; defaults to the instance's timeout.
        :param **params: Optional placeholder values forwarded to the locator registry for
                         selector interpolation.
        :returns: Self for fluent chaining.
        :raises NoSuchElementException: If the frame element cannot be located.
        :raises TimeoutException: If the frame element is not present within the timeout.
        """
        to = timeout or self.default_timeout
        el = self.find_element(page, name, wait="present", timeout=to, **params)
        logger.info(f"Switch to frame {page}.{name}({params})")
        self.driver.switch_to.frame(el)
        return self

    def switch_to_parent_frame(self) -> "UiActions":
        """
        Switch the driver's context to the **parent** frame.

        :returns: Self for fluent chaining.
        """
        logger.info("Switch to parent frame")
        self.driver.switch_to.parent_frame()
        return self

    def switch_to_default_content(self) -> "UiActions":
        """
        Switch the driver's context back to the **top-level document**.

        :returns: Self for fluent chaining.
        """
        logger.info("Switch to default content")
        self.driver.switch_to.default_content()
        return self

    # -----------------------
    # Windows / Tabs
    # -----------------------
    def switch_to_new_window(self) -> "UiActions":
        """
        Switch the driver's context to the **most recently opened** window/tab.

        :returns: Self for fluent chaining.
        """
        logger.info(f"Window handles (before): {self.driver.window_handles}")
        for h in self.driver.window_handles:
            self.driver.switch_to.window(h)
        logger.info("Switched to last window handle")
        return self

    def switch_to_window(self, index: int) -> "UiActions":
        """
        Switch the driver's context to a window/tab by **index**.

        :param index: Zero-based index in `driver.window_handles`.
        :returns: Self for fluent chaining.
        :raises IndexError: If `index` is out of range.
        """
        handles = self.driver.window_handles
        logger.info(f"Window handles: {handles}")
        if not (0 <= index < len(handles)):
            raise IndexError(f"Window index {index} out of range; have {len(handles)}")
        self.driver.switch_to.window(handles[index])
        logger.info(f"Switched to window[{index}] handle={handles[index]}")
        return self

    # -----------------------
    # Alerts
    # -----------------------
    def accept_alert(self) -> "UiActions":
        """
        Accept the active JavaScript alert, if present.

        :returns: Self for fluent chaining.
        :raises TimeoutException: If no alert appears within the default short timeout.
        """
        WebDriverWait(self.driver, self.sec5).until(EC.alert_is_present())
        self.driver.switch_to.alert.accept()
        logger.info("Alert accepted")
        return self

    def dismiss_alert(self) -> "UiActions":
        """
        Dismiss the active JavaScript alert, if present.

        :returns: Self for fluent chaining.
        :raises TimeoutException: If no alert appears within the default short timeout.
        """
        WebDriverWait(self.driver, self.sec5).until(EC.alert_is_present())
        self.driver.switch_to.alert.dismiss()
        logger.info("Alert dismissed")
        return self

    def get_alert_text(self) -> str:
        """
        Return the text of the active JavaScript alert.

        :returns: Alert text as a string.
        :raises TimeoutException: If no alert appears within the default short timeout.
        """
        WebDriverWait(self.driver, self.sec5).until(EC.alert_is_present())
        txt = self.driver.switch_to.alert.text
        logger.info(f"Alert text: {txt!r}")
        return txt

    # -----------------------
    # Low-level helpers
    # -----------------------
    def get_page_source(self) -> str:
        """
        Return the full HTML **page source**.

        :returns: HTML source as a string.
        """
        return self.driver.page_source

    def quit(self) -> None:
        """
        Quit the WebDriver session and close all windows.

        :returns: None
        """
        self.driver.quit()

    # -------------------------
    # Assertion Related methods
    # -------------------------

    def assert_title_is(self, expected: str, timeout: Optional[int] = None) -> "UiActions":
        """
        Assert that the current page title exactly matches `expected` within `timeout`.

        :param expected: Exact page title expected.
        :param timeout: Override timeout (seconds) for this call; defaults to the instance's timeout.
        :returns: Self for fluent chaining.
        :raises TimeoutException: If the title does not match within the timeout.
        """
        to = timeout or self.default_timeout
        logger.info(f"Asserting title equals: {expected!r} (timeout={to}s)")
        WebDriverWait(self.driver, to).until(EC.title_is(expected))
        return self

    def verify_page_header_if_present(self, page: str, *, wait: str = "visible",
                                      timeout: Optional[int] = None) -> bool:
        """
        If the standardized locator 'page_heading' exists for this page, fetch its text using the
        existing get_text(page, name, wait=..., timeout=...) and assert it equals the page key (normalized).
        If the locator is not present (or not found quickly), return False (not applicable).
        If present but text mismatches, raise AssertionError.

        :param page: Page key (also used as expected header text).
        :param wait: One of {"present", "visible", "clickable"} controlling how the header is waited for.
                     Defaults to "visible".
        :param timeout: Optional per-candidate timeout forwarded to get_text. If None, a short (~2s)
                        detection window is used.
        :returns: True if header existed and matched; False if header not applicable/not found quickly.
        """
        # Import here to avoid coupling if you run without the exception type in scope
        try:
            from utilities.locator_registry import LocatorError  # type: ignore
        except Exception:
            LocatorError = RuntimeError  # fallback typing; won't be used if registry is present

        try:
            actual = self.get_text(page, "page_heading", wait=wait, timeout=timeout or 2)
        except (TimeoutException, NoSuchElementException, LocatorError):
            # Header not applicable or not found quickly: treat as "not applicable"
            return False

        if _normalize_text(actual) != _normalize_text(page):
            raise AssertionError(
                f"Header text mismatch for page {page!r}. "
                f"Expected: {page!r}, Actual: {actual!r}"
            )
        return True

    def verify_page_url_matches_registry(
            self,
            page: str,
            *,
            strict: bool = False,
            timeout: Optional[int] = None,
            poll_frequency: float = 0.25,
    ) -> "UiActions":
        """
        Wait for the current URL to match the page spec defined in the locator registry.

        Priority:
          1) If YAML provides `url_regex`, the current URL MUST match that regex.
          2) Else if strict=True, the current URL MUST equal `page_url`.
          3) Else (default), the current URL MUST start with `page_url` (prefix match).

        :param page: Page key in the registry (e.g., "ContactDetails").
        :param strict: Force exact match against page_url when no regex is provided.
        :param timeout: Max seconds to wait; defaults to this instance's default timeout.
        :param poll_frequency: How often to poll the URL while waiting.
        :returns: Self for fluent chaining.
        :raises AssertionError: If no spec exists or the URL doesn't match within `timeout`.
        """
        to = timeout or self.default_timeout
        expected_url, compiled_regex = get_page_url_spec(page)

        if compiled_regex is not None:
            # Wait until the regex matches the entire URL (anchor your YAML regex with ^...$ if desired)
            try:
                WebDriverWait(self.driver, to, poll_frequency=poll_frequency).until(
                    lambda d: compiled_regex.match(d.current_url) is not None
                )
                logger.info(f"URL match OK for page '{page}' (regex).")
                return self
            except TimeoutException:
                actual = self.get_current_url()
                raise AssertionError(
                    f"URL did not match regex for page '{page}' within {to}s.\n"
                    f"Regex: {compiled_regex.pattern}\nActual: {actual}"
                )

        # Fallback to page_url if no regex is configured
        if not expected_url:
            raise AssertionError(f"No page_url/url_regex configured for page {page!r}.")

        def _ok(url: str) -> bool:
            return url == expected_url if strict else url.startswith(expected_url)

        try:
            WebDriverWait(self.driver, to, poll_frequency=poll_frequency).until(
                lambda d: _ok(d.current_url)
            )
            mode = "strict" if strict else "prefix"
            logger.info(f"URL match OK for page '{page}' ({mode}).")
            return self
        except TimeoutException:
            actual = self.get_current_url()
            mode = "exactly" if strict else "to start with"
            raise AssertionError(
                f"URL did not match for page '{page}' within {to}s.\n"
                f"Expected {mode}: {expected_url}\nActual: {actual}"
            )

    def assert_all_locators_present(
            self,
            page: str,
            *,
            wait: str = "present",
            timeout: Optional[int] = None,
            **params: Any,
    ) -> None:
        """
        Assert that every locator defined under `page` is present.
        Consumes the existing generator from the locator registry. If any element cannot be
        located, the generator (or the underlying locate) will raise, failing this assertion.

        :param page: Page key (case-sensitive).
        :param wait: "present" | "visible" | "clickable" used for locating each element.
        :param timeout: per-candidate timeout (defaults to instance default if None).
        :raises TimeoutException: if any element is missing or not found in time.
        :raises LocatorError: if a page/locator is misconfigured.
        """
        # Lazy import so we don't touch the registry at module import time
        from utilities.locator_registry import generate_elements  # type: ignore

        # Resolve timeout without relying on _resolve_timeout
        to = int(timeout if timeout is not None else getattr(self, "default_timeout", 10))

        # Consume the generator; it will raise on the first missing element (skip_missing=False)
        for _name, _el in generate_elements(
                self.driver,
                page,
                names=None,  # all keys under the page
                wait=wait,
                timeout=to,
                skip_missing=False,
                page_load_only=True,
                **params,
        ):
            pass

    def assert_message_text(
            self,
            page: str,
            name: str,
            expected: str,
            *,
            wait: str = "visible",
            poll_frequency: float = 0.0,
            timeout: Optional[int] = None,
    ) -> "UiActions":
        """
        Assert that the element identified by (page, name) has the expected text.

        Notes:
          - Uses get_text(page, name, wait=..., timeout=...) so the wait mode is controllable.
          - Text is compared after whitespace normalization.

        :param poll_frequency: Frequency of check for fluent wait.
        :param page: Page name (top-level key) from the locator registry.
        :param name: Locator key under the page (the message element).
        :param expected: Expected message string from data.
        :param wait: One of {"present", "visible", "clickable"}; defaults to "visible".
        :param timeout: Override timeout (seconds); defaults to a small value if None.
        :returns: Self for fluent chaining.
        :raises AssertionError: If the actual text does not match the expected text.
        """
        actual = self.highlight_element(page, name).get_text(page, name, wait=wait,
                                        poll_frequency=poll_frequency, timeout=timeout or 5)
        if _normalize_text(actual) != _normalize_text(expected):
            raise AssertionError(
                f"Message text mismatch for {page}.{name}.\n"
                f"Expected: {expected!r}\n"
                f"Actual:   {actual!r}"
            )
        return self

    def assert_message_text_from_dataset(
            self,
            page: str,
            name: str,
            dataset: Dict[str, Any],
            dataset_name: Optional[str] = None,
            *,
            wait: str = "visible",
            timeout: Optional[int] = None,
    ) -> "UiActions":
        """
        Assert message text by looking up the expected string from the loaded dataset.

        Data key convention:
          <page_lower>_assert_<name>

        Where:
          - page_lower = page with spaces removed, lowercased
          - name       = the locator key for the message element

        :param page: Page name as used in locator YAML (case-sensitive).
        :param name: Locator key of the message element under that page.
        :param dataset: The loaded dataset mapping (e.g., context.dataset).
        :param dataset_name: Optional dataset label for clearer error messages.
        :param wait: One of {"present", "visible", "clickable"}; defaults to "visible".
        :param timeout: Override timeout (seconds); defaults to a small value if None.
        :returns: Self for fluent chaining.
        :raises AssertionError: If dataset is missing, key not found, or text mismatch occurs.
        """
        if not dataset:
            raise AssertionError(
                "No dataset loaded. Ensure you ran: Given I dataset \"<DATASET_NAME>\" is loaded for the scenario."
            )
        page_key = page.replace(" ", "").lower()
        data_key = f"{page_key}_assert_{name}"
        if data_key not in dataset:
            available = ", ".join(sorted(k for k in dataset.keys() if
                                         k.startswith(page_key + "_assert_"))) or "(none)"
            raise AssertionError(
                f"Expected message key '{data_key}' not found in dataset '{dataset_name or '(unknown)'}'. "
                f"Available keys for page '{page_key}': {available}"
            )
        expected = str(dataset[data_key])
        return self.assert_message_text(page, name, expected, wait=wait, timeout=timeout)
