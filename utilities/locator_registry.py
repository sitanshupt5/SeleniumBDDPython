import os
import yaml
import re
from typing import Dict, List, Tuple, Optional, Any, Iterable, Iterator, Pattern
from pathlib import Path
from functools import lru_cache

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ExpectedConditions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common import TimeoutException, NoSuchElementException
from yaml import YAMLError

from utilities.custom_logger import LogGen

logger = LogGen.loggen("LocatorRegistry")


class LocatorError(RuntimeError):
    """Raised when locator configuration or resolution fails"""


_by_map: Dict[str, str] = {
    "css": By.CSS_SELECTOR,
    "css_selector": By.CSS_SELECTOR,
    "xpath": By.XPATH,
    "id": By.ID,
    "name": By.NAME,
    "class": By.CLASS_NAME,
    "class_name": By.CLASS_NAME,
    "tag": By.TAG_NAME,
    "tag_name": By.TAG_NAME,
    "link_text": By.LINK_TEXT,
    "partial_link_text": By.PARTIAL_LINK_TEXT,
}

_page_meta: Dict[str, Dict[str, str]] = {}


def _project_root() -> str:
    """
    Compute the project root as the directory containing this file's parent.
    Expected layout in the project repo:
        <project_root>/
          utilities/locator_registry.py     <-- this file
          <application>/pages/*.yml
    :return: Root path of the project in string format.
    """
    return str(Path(__file__).resolve().parent.parent)


def _page_dirs() -> List[str]:
    """
    Return all `<project_root>/<application>/pages` directories.

    Rule:
    - <application> is any **immediate** child directory of project root
      that contains a subdirectory named 'pages'.
    :return: List of directory path containing subfolder 'pages' as string.
    """
    root = Path(_project_root())
    results: List[str] = []
    for child in root.iterdir():
        if child.is_dir():
            pages = child / "pages"
            if pages.is_dir():
                results.append(str(pages))
    return results


def _load_yaml(path: str) -> Dict[str, Any]:
    """
    Load single yaml file and return its dictionary
    :param path: Path to the .yml/.yaml file as a string.
    :return LocatorError: Incase the file is not found in the path or cannot be parsed to a
    dict
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except FileNotFoundError as e1:
        raise LocatorError(f"YAML file not found at path {path}") from e1
    except PermissionError as e2:
        raise LocatorError(f"Access denied for reading yaml file at path {path}") from e2
    except YAMLError as e3:
        raise LocatorError(f"Invalid yaml syntax in file at path {path}.\n{e3}")
    except Exception as e4:
        raise LocatorError(f"Unexpected Error occured while parsing yaml at {path}.\n{e4}")

    if not isinstance(data, dict):
        raise LocatorError(f"Top-Level YAML must be a mapping: {path}")
    return data


def _parse_line_strict(line: str) -> Tuple[str, str]:
    """
    Parse a locator line of the exact form "<strategy>, <value>".
    \nExamples:
      "xpath, //div[@id='x']"    -> (By.XPATH, "//div[@id='x']")\n
      "css, div#x"               -> (By.CSS_SELECTOR, "div#x")
    :param line: Combined string of locator strategy and locator value separated by comma.
    :return: Tuple containing separate strings of locator strategy and value
    :raises LocatorError: If the line is not a str, missing comma, or strategy unknown.
    """
    if not isinstance(line, str):
        raise LocatorError(f"Locator enty must be string. Got: {type(line).__name__}")
    if "," not in line:
        raise LocatorError(f"Locator line must use comma format, eg. '<strategy>, <value>'. "
                           f"Got: {line!r}")

    strat_raw, value = line.split(",", 1)
    strat = strat_raw.strip().lower()
    value = value.strip()
    # Remove optional trailing ', page_load_check' marker
    value = re.sub(r",\s*page_load_check\s*$", "", value, flags=re.IGNORECASE)

    by = _by_map.get(strat)
    if not by:
        raise LocatorError(f"Strategy identifier {strat!r} used in line {line!r} is invalid.\n"
                           f"Accepted values of strategy identifier: 'class', 'class_name', "
                           f"'css', 'css_selector', 'id', 'link_text', 'name', "
                           f"'partial_link_text', 'tag', 'tag_name', 'xpath'. ")
    if not value:
        raise LocatorError(f"No locator value found in line {line!r}")

    return by, value


def _format_selector(selector: str, **params: Any) -> str:
    """
    Interpolate '{placeholders}' in the selector using str.format. If not placeholders
    exist, returns the placeholder unchanged.
    :param selector: The raw selector/locator value which may contain placeholders.
    :param params: Values for placeholders.
    :return: if a placeholder is missing a provided value.
    """
    if "{" not in selector:
        return selector
    try:
        return selector.format(**params)
    except KeyError as exc:
        missing = str(exc).strip("'")
        raise LocatorError(f"Missing placeholder value for: {missing!r} in {selector!r} from exc")


@lru_cache(maxsize=1)
def _scan_all() -> Dict[str, Dict[str, List[str]]]:
    """
    Scan all <project_root>/<application>/<pages/*.yml files and build the registry:
    {
        "PageName":{
            "element_key": [ "<strategy>, <value>", ...],
            ...
        },
        ...
    }
    Also, populates _page_meta  for each PageName with any 'page_url'/'page_title'.
    :return: Dictionary of page_name against dictionary of locators. The dictionary of
    locators consists of key-value pairs of locator key against corresponding list of
    selectors in string format(e.g.: "<strategy>, <selector_value>")
    :raises LocatorError: If no pages are found or if a page file violates the schema.
    """
    _page_meta.clear()
    registry: Dict[str, Dict[str, List[str]]] = {}

    page_dirs = _page_dirs()
    if not page_dirs:
        raise LocatorError(f"No page directories found. Expected atleast one "
                           f"<application>/pages under {_project_root()}")

    files: List[Path] = []
    for d in page_dirs:
        files.extend(sorted(Path(d).glob("*.yml")))
        files.extend(sorted(Path(d).glob("*.yaml")))

    if not files:
        raise LocatorError("No YAML page files found under any <applicaton>/pages directory.")

    for path in files:
        data = _load_yaml(str(path))
        for page_name, page_block in data.items():
            if not isinstance(page_name, str) or not page_name:
                raise LocatorError(f"Invalid page name in {path}: {page_name!r}")
            if not isinstance(page_block, dict):
                raise LocatorError(f"Page block must be a mapping: {page_name} in {path}")

            meta: Dict[str, Any] = {}
            if "page_url" in page_block:
                if not isinstance(page_block["page_url"], (str, type(None))):
                    raise LocatorError(f"page_url must be a string for {page_name} page at "
                                       f"path {path}")
                meta["page_url"] = page_block["page_url"]
            if "page_title" in page_block:
                if not isinstance(page_block["page_title"], (str, type(None))):
                    raise LocatorError(f"page_title must be a string for {page_name} page at "
                                       f"path {path}")
                meta["page_title"] = page_block["page_title"]
            if "url_regex" in page_block:
                if page_block["url_regex"] is not None and not isinstance(
                        page_block["url_regex"], str):
                    raise LocatorError(
                        f"url_regex must be a string for {page_name} page at path {path}")
                meta["url_regex"] = page_block["url_regex"]

            if meta:
                _page_meta[page_name] = meta

            locs = page_block.get("locators")
            if not isinstance(locs, dict):
                raise LocatorError(f"Missing or invalid locators mapping for page "
                                   f"{page_name} in {path}")

            normalized: Dict[str, List[str]] = {}
            for key, value in locs.items():
                if not isinstance(key, str) or not key:
                    raise LocatorError(f"Invalid element key under page {page_name} at path "
                                       f"{path} : {key!r}")
                if isinstance(value, str):
                    lines = [value]
                elif isinstance(value, list) and all(isinstance(s, str) for s in value):
                    lines = value
                else:
                    raise LocatorError(f"Locators for '{page_name}.{key}' must be a string "
                                       f"or a list of strings")

                for line in lines:
                    _parse_line_strict(line)

                normalized[key] = lines

            registry.setdefault(page_name, {}).update(normalized)
    return registry


def _clear_cache() -> None:
    """
    Clear in-memory caches  so that subsequent lookups rescan  the YAML files.
    Call this after updating any page file on the disk during run time.
    """
    _page_meta.clear()
    _scan_all().cache_clear()  # type: ignore[attr-defined]


def page_meta(page: str) -> Dict[str, Any]:
    """
    Return a **copy** of page metadata for 'page'(e.g. page_url, page_title, url_regex), or an empty
    dict if none recorded.
    :param page: Page name (case-sensitive, must match the YAML key)
    :return: A dictionary with key-value pairs of 'page_name' and page metadata dictionary
    respectively or an empty dictionary.
    """
    _ = _scan_all()
    return dict(_page_meta.get(page, {}))


def page_url(page: str) -> Optional[str]:
    """
    Convenience accessor for 'page_meta(page).get("page_url")'.
    :param page: Page name (case-sensitive, must match the YAML key)
    :return: String value for 'page_url' if present, None otherwise.
    """
    return page_meta(page).get('page_url')  # type: ignore[return-value]


def page_title(page: str) -> Optional[str]:
    """
    Convenience accessor for 'page_meta(page).get("page_title")'.
    :param page: Page name (case-sensitive, must match the YAML key)
    :return: String value for 'page_title' if present, None otherwise.
    """
    return page_meta(page).get('page_title')  # type: ignore[return-value]


def page_url_regex(page: str) -> Optional[str]:
    """
    Return the raw url_regex string for the page, if configured; otherwise None.
    """
    return page_meta(page).get("url_regex")


@lru_cache(maxsize=None)
def get_page_url_spec(page: str) -> Tuple[Optional[str], Optional[Pattern[str]]]:
    """
    Return (page_url, compiled_url_regex) for the given page.
    If 'url_regex' is defined in YAML, compile it and return the compiled Pattern.
    Raises LocatorError if the page is unknown or the regex is invalid.

    :param page: Page key in the registry (case-sensitive)
    :returns: (page_url or None, compiled_regex or None)
    """
    _ = _scan_all()  # ensure registry is loaded
    meta = _page_meta.get(page)
    if meta is None:
        raise LocatorError(f"Page '{page}' not found in locator registry.")

    page_url: Optional[str] = meta.get("page_url")
    url_regex_str: Optional[str] = meta.get("url_regex")

    compiled: Optional[Pattern[str]] = None
    if url_regex_str:
        try:
            compiled = re.compile(url_regex_str)
        except re.error as e:
            raise LocatorError(f"Invalid url_regex for page '{page}': {e}") from e

    return page_url, compiled


def candidates(page: str, name: str, **params: Any) -> List[Tuple[str, str]]:
    """
    Resolve (page, element name) to an **ordered** list of (By, selector) tuples.
        - page and element keys are matched **exactly** (case-sensitive).
        - Each locator line must be of the format '<strategy>, <value>' and is validated at
          load time.
        - This function also applies placeholder interpolation to selector values using
          'str.format(**params)'.
    :param page: Page name (case-sensitive, must match the YAML key).
    :param name: Element key under that page (exact match).
    :param params: Placeholder values for selectors (e.g. row_id=123).
    :return: Ordered list of (By, selector) tuples.
    :raises LocatorError: If page/element not found or locator missing.
    """
    reg = _scan_all()

    page_block = reg.get(page)
    if page_block is None:
        raise LocatorError(f"Unknown page: '{page}'")

    lines = page_block.get(name)
    if not lines:
        raise LocatorError(f"Unkown locator '{name}' under page '{page}'")

    results: List[Tuple[str, str]] = []
    for line in lines:
        by, raw_selector = _parse_line_strict(line)
        selector = _format_selector(raw_selector, **params)
        results.append((by, selector))

    return results


def locate(driver: WebDriver, page: str, name: str, *, wait: str = 'present',
           poll_frequency: float = 0.0, timeout: int = 6, **params: Any) -> WebElement:
    """
    Locate an element by trying  each candidate locator (in order) with a wait.

    Wait modes:
      - "present" -> EC.presence_of_element_located
      - "visible" -> EC.visibility_of_element_located
      - "clickable" -> EC.element_to_be_clickable

    Notes:
      - timeout applies **per candidate**.
      - Raises TimeoutException is none of the candidates succeed in time.

    :param poll_frequency: Frequency of check for fluent wait.
    :param driver: Selenium WebDriver instance.
    :param page: Page name (case-sensitive, must match the YAML key)
    :param name: Element key under that page (exact match).
    :param wait: One of {"present", "visible", "clickable"}
    :param timeout: Timeout in seconds per candidate.
    :param params: Placeholder values for selector interpolation.
    :return: (WebElement, (By, Selector)) for the candidate that succeeded.
    :raises LocatorError: configuration or placeholder errors.
    :raises TimeoutException: if all candidates fail within their timeouts.
    """
    wait = wait.lower().strip()
    if wait == "present":
        def _condition(locator):  # noqa: N801
            return ExpectedConditions.presence_of_element_located(locator)
    elif wait == "visible":
        def _condition(locator):  # noqa: N801
            return ExpectedConditions.visibility_of_element_located(locator)
    elif wait == "clickable":
        def _condition(locator):  # noqa: N801
            return ExpectedConditions.element_to_be_clickable(locator)
    else:
        raise LocatorError(
            f'Unknown wait mode: "{wait}" (expected: present|visible|clickable)')
    last_exc: Optional[Exception] = None
    for by, selector in candidates(page, name, **params):
        try:
            elem = WebDriverWait(driver, timeout, poll_frequency=poll_frequency).until(_condition((by,
                                                                                      selector)))
            return elem
        except (TimeoutException, NoSuchElementException) as exc:
            last_exc = exc
            continue

    raise TimeoutException(
        f'Element "{page}.{name}" not found for any candidate within  {timeout}s per '
        f'candidate.\n Last Error: {last_exc}'
    )


def generate_elements(driver: WebDriver, page: str, names: Optional[Iterable[str]], *,
                      wait: str = 'present', timeout: int = 5, skip_missing: bool = False,
                      page_load_only: bool = False,**params: Any) -> Iterator[Tuple[str, WebElement]]:
    """
    Generator that yields one element at a time from a page.
    Yields items in the form:
      (element_name, WebElement)

    Selection & ordering:
      - If 'names'  is provided (Iterable of element keys), elements are attempted in that
        order.
      - Otherwise, all element keys under the page are used in natural dict order

    Lookup Behavior:
      - For each candidate uses the same multi-candidate fallback as 'locate(...)'
      - On first successful candidate, yields and moved to the next element.

    Error Behavior:
      - If an element can't be located:
        * If 'skip_missing' is False (default), raises TimeoutException immediately.
        * If 'skip_missing' is True, silently skips that element and continues.

    :param page_load_only: Decides whether the element generated need to be verified at page load time.
    :param driver: Selenium WebDriver instance.
    :param page: Page name (case-sensitive; must match YAML key).
    :param names: Optional iterable of element keys (case-sensitive) to control which
                  elements are yielded and in what order.
    :param wait: One of {"present", "visible", "clickable"}; defaults to "present".
    :param timeout: Timeout in seconds per candidate.
    :param skip_missing: If True, skip elements that fail to be located; otherwise raise.
    :param params: Placeholder values forwarded to selector formatting.
    :returns: Iterator of (name, WebElement) for each successfully located element.
    :raises LocatorError: If page doesn’t exist or configuration errors occur.
    :raises TimeoutException: If an element cannot be located (unless skip_missing=True).
    """
    reg = _scan_all()

    page_block = reg.get(page)
    if page_block is None:
        raise LocatorError(f"Unknown page: '{page}'")

    # Build initial list of keys to iterate
    if names is not None:
        keys = list(names)
    else:
        keys = list(page_block.keys())

    # Optionally restrict to only locators explicitly marked for page-load checks.
    # A locator entry is "page-load" if any of its candidate strings includes
    # the token 'page_load_check' (case-insensitive), e.g.:
    #   "xpath, //div[@id='header'], page_load_check"
    if page_load_only:
        eligible = []
        for k in keys:
            cand = page_block.get(k)
            cand_list = cand if isinstance(cand, (list, tuple)) else [cand]
            has_flag = any(
                isinstance(c, str) and 'page_load_check' in c.lower() for c in cand_list)
            if has_flag:
                eligible.append(k)
        keys = eligible

    for name in keys:
        if 'menu' not in name:
            try:
                elem = locate(driver, page, name, wait=wait, timeout=timeout, **params)
                yield name, elem
            except TimeoutException:
                if skip_missing:
                    continue
                raise
