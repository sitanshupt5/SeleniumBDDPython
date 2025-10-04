from os.path import exists
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

import yaml
from yaml import YAMLError
from selenium.webdriver.common.by import By

from utilities.custom_logger import LogGen
from utilities.ui_actions import UiActions

logger = LogGen.loggen("DataRegistry")


class DataError(RuntimeError):
    """Raised when there is a problem loading, parsing, or using test data."""


def _find_application_root_from_feature(feature_path:Path) -> Path:
    """
    Walk up from <...>/<application>/features/**/<file>.feature to locate the <application> folder
    by finding the ancestor directory named 'features' and taking its parent.

    :param feature_path: Absolute path to the .feature file being currently executed.
    :return: Path to the <application> directory.
    :raises DataError: If not 'features' ancestor is found.
    """
    p = feature_path.resolve()
    for ancestor in [p.parent] + list(p.parents):
        if ancestor.name == "features":
            return ancestor.parent
    raise DataError(
        f"Could not determine application root for the feature: {feature_path}"
        f"(no features ancestor found)"
    )

def get_data_file(feature_filename: str) -> str:
    """
    Build the expected datafile path for the running feature.
    Naming Rule:
        <application>/data/<feature_stem>_data.yml
    :param feature_filename: Feature file path as provided by Behave (feature.filename).
    :return: Absolute path the expected yaml datafile (string)
    """
    feature_path = Path(feature_filename).resolve()
    app_root = _find_application_root_from_feature(feature_path)
    data_dir = app_root/"data"
    stem = feature_path.stem
    data_file = data_dir/f"{stem}_data.yml"
    return str(data_file)


def parse_data_file(path: str) -> Dict[str, Dict[str, Any]]:
    """
    Load and validate the feature data YAML.
    Structure:
        <dataset_name>:
            <page_field_type_key>: <value>
    :param path: Absolute path to the <feature>_data.yml
    :return: Dict mapping  dataset name -> dataset mapping.
    :raises DataError: When file missing, invalid YAML, or top-level not a mapping.
    """
    p = Path(path)
    if not exists(p):
        raise DataError(f"Data file not found at path: {path}")
    try:
        with p.open("r", encoding = 'utf-8') as f:
            data = yaml.safe_load(f)
    except YAMLError as  e1:
        raise DataError(f"Invalid YAML in datafile at path '{path}'.\n{e1}")
    except Exception as e2:
        raise DataError(f"Failed to read data file at path '{path}'.\n{e2}")

    if not isinstance(data, dict):
        raise DataError(f"Top-level of data file must be a mapping. Filepath: {path}")

    for ds_name, ds in data.items():
        if not isinstance(ds, dict):
            raise DataError(f"Dataset '{ds_name}' must be a mapping. Filepath: {path}")
    return data     # type: ignore[return-value]


def extract_dataset(data: Dict[str, Dict[str, Any]], dataset_name: str) -> Dict[str, Any]:
    """
    Extract a dataset by name from the already-parsed data file.

    :param data: Parsed data_file_content (mapping of dataset -> mapping).
    :param dataset_name: The dataset (top-level key) to use for the scenario.
    :returns: The dataset mapping (field-key -> value).
    :raises DataError: If dataset is not present.
    """
    ds = data.get(dataset_name)
    if ds is None:
        raise DataError(
            f"Dataset '{dataset_name}' not found in the data file."
            f"Available: {', '.join(sorted(data.keys())) or '(none)'}"
        )
    return ds

def _split_key(key: str) -> Tuple[str, str, str]:
    """
    Parse key naming convention:
        <page_name>_<field_name>_<field_type>

    - page_name: first segment (lowercase in data file)
    - field_type: last segment (one of accepted values)
    - field_name: middle (can contain underscores)

    :param key: Raw key from the dataset mapping.
    :returns: (page_name, field_name, field_type)
    :raises DataError: If the key doesn't contain at least 3 segments.
    """
    parts = key.split("_")
    if len(parts) < 3:
        raise DataError(
            f"Invalid data key '{key}'. Expected '<page>_<field>_<type>' with at least 3 segments."
        )
    page = parts[0]
    ftype = parts[-1]
    fname = "_".join(parts[1:-1])
    return page, fname, ftype


def map_data_to_fields(actions, page: str, dataset: Dict[str, Any]) -> None:
    """
    Populate fields for a single page from a scenario dataset.

    Invocation pattern:
      Called by a step like:
        When I populate the fields in "CreateNewContact" with corresponding data.

      - The step passes `page` exactly as in page YAML (case-sensitive).
      - The dataset (e.g., context.dataset) may include entries for multiple pages.
      - This function processes **only** dataset entries whose page segment matches `page`
        (using lowercase comparison as per the data-file convention).

    Dataset key format (strict):
        <page_name>_<field_name>_<field_type>

      • page_name  : lowercase page key used in data files (e.g., "createnewcontact").
      • field_name : can contain underscores (everything between first and last segments).
      • field_type : one of:
            input         -> String;  text to be entered into the field.
            checkbox      -> Boolean; desired checkbox state (True/False).
            radio         -> Boolean; desired radio state (True/False). Clicks <field_name>_true or <field_name>_false.
            selectvalue   -> String;  <option value="..."> for a native <select>.
            selectindex   -> Integer; 0-based index for a native <select>.
            selecttext    -> String;  visible text for a native <select>.
            dbutton       -> Boolean; for custom dropdown opener: True = click required; False = click not required.
            dlist         -> String;  for custom dropdown menu/list: option text to select.
            calendar      -> Not implemented yet; raises a clear error.

    Custom dropdown conventions (dbutton + dlist):
      • The dropdown **opener** locator key is the field_name used with **dbutton**, e.g., "status_dropdown".
      • The dropdown **menu/list container** locator key is the field_name used with **dlist**, and it
        must end with the suffix "_menu", e.g., "status_dropdown_menu".
      • In data.yml, the two keys for the same dropdown share the same base:
            createnewcontact_status_dropdown_dbutton
            createnewcontact_status_dropdown_menu_dlist
        Here, base is "status_dropdown" and the menu/list key is "status_dropdown_menu".
      • Both entries must be present for the same dropdown; otherwise a DataError is raised.
      • When dbutton == True, we will open + pick via actions.pick_from_custom_dropdown(...).
        When dbutton == False, we will NOT click the opener; we select directly from the provided menu container.

    Behavior:
      • Only entries matching the given `page` (by lowercase page segment) are processed.
      • Dispatch uses existing UiActions methods (type_text, click, select_by_* for native selects,
        pick_from_custom_dropdown for custom dropdowns).
      • Fails fast with DataError on invalid types, missing dbutton/dlist pairing, or type mismatches.

    :param actions: UiActions instance bound to a WebDriver.
    :param page: Page key exactly as in the page YAML (case-sensitive). Used for all UiActions calls.
    :param dataset: Mapping of "<page_lower>_<field_name>_<field_type>" -> value.
    :returns: None
    :raises DataError: On invalid/missing pairs, wrong types, or not-implemented calendar input.
    """
    def _norm_page_for_data(s: str) -> str:
        # Data uses lowercase page names; strip spaces defensively.
        return s.replace(" ", "").lower()

    page_data_key = _norm_page_for_data(page)

    # Group dbutton/dlist by base field; process other types immediately.
    dropdown_groups: Dict[str, Dict[str, Any]] = {}   # base -> { opener_name, menu_name, dbutton, dlist }
    immediate_ops: list[Tuple[str, str, Any]] = []    # (field_name, field_type, value)

    for raw_key, value in dataset.items():
        raw_key = str(raw_key)
        ds_page, field_name, ftype = _split_key(raw_key)  # reuse existing helper in this module
        if ds_page != page_data_key:
            continue  # ignore entries for other pages in this dataset

        if ftype in {"dbutton", "dlist"}:
            if ftype == "dbutton":
                if field_name.endswith("_menu"):
                    raise DataError(
                        f"dbutton key must reference the dropdown opener (should not end with '_menu'): '{raw_key}'"
                    )
                base = field_name
                grp = dropdown_groups.setdefault(base, {})
                grp["opener_name"] = field_name
                grp.setdefault("menu_name", f"{base}_menu")
                grp["dbutton"] = value
            else:  # ftype == "dlist"
                if not field_name.endswith("_menu"):
                    raise DataError(
                        f"dlist key must reference the dropdown menu container and end with '_menu': '{raw_key}'"
                    )
                base = field_name[:-5]  # strip "_menu"
                grp = dropdown_groups.setdefault(base, {})
                grp["menu_name"] = field_name
                grp.setdefault("opener_name", base)
                grp["dlist"] = value
        else:
            immediate_ops.append((field_name, ftype, value))

    # Execute non-paired operations first
    for field, ftype, val in immediate_ops:
        if ftype == "input":
            actions.type_text(page, field, str(val), clear=True)

        elif ftype == "checkbox":
            if not isinstance(val, bool):
                raise DataError(f"Checkbox value must be boolean for '{page}.{field}', got: {val!r}")
            el = actions.find_element(page, field, wait="visible")
            currently = bool(el.is_selected())
            if val and not currently:
                actions.click(page, field)
                logger.info(f"Checked the {field} {ftype}.")
            elif not val and currently:
                actions.click(page, field)
                logger.info(f"Unchecked the {field} {ftype}.")

        elif ftype == "radio":
            if not isinstance(val, bool):
                raise DataError(f"Radio value must be boolean for '{page}.{field}', got: {val!r}")
            suffix = "true" if val else "false"
            actions.click(page, f"{field}_{suffix}")
            logger.info(f"Turned the {field} {ftype} to {val}.")

        elif ftype == "selectvalue":
            actions.select_by_value(page, field, str(val))

        elif ftype == "selectindex":
            try:
                idx = int(val)
            except Exception:
                raise DataError(f"selectindex requires integer value for '{page}.{field}', got: {val!r}")
            actions.select_by_index(page, field, idx)

        elif ftype == "selecttext":
            actions.select_by_visible_text(page, field, str(val))

        elif ftype == "calendar":
            raise DataError(
                f"Calendar input not implemented yet. Field: '{page}.{field}', value: {val!r}"
            )

        elif 'assert' in field:
            continue

        else:
            raise DataError(f"Unsupported field_type '{ftype}' for '{page}.{field}'")

    # Validate and execute custom dropdown groups (dbutton + dlist)
    for base, grp in dropdown_groups.items():
        missing = [k for k in ("opener_name", "menu_name", "dbutton", "dlist") if k not in grp]
        if missing:
            raise DataError(
                f"Custom dropdown requires opener/menu/dbutton/dlist for '{page}.{base}'. "
                f"Missing: {', '.join(missing)}"
            )

        opener_name = grp["opener_name"]
        menu_name = grp["menu_name"]
        dbutton_val = grp["dbutton"]
        dlist_val = grp["dlist"]

        # Type checks
        if not isinstance(dbutton_val, bool):
            raise DataError(
                f"dbutton must be boolean for '{page}.{opener_name}', got: {dbutton_val!r}"
            )
        if not isinstance(dlist_val, str):
            raise DataError(
                f"dlist must be string (option text) for '{page}.{menu_name}', got: {dlist_val!r}"
            )

        if dbutton_val is True:
            # Open + pick via existing UiActions helper (clicks opener internally)
            actions.pick_from_custom_dropdown(
                opener_page=page,
                opener_name=opener_name,
                option_text=dlist_val,
                menu_page=page,
                menu_name=menu_name,
            )
        else:
            # dbutton == False → do NOT click opener; select directly within the provided menu container
            menu_el = actions.find_element(page, menu_name, wait="visible")
            # Build a safe XPath literal for the option text
            q = f"'{dlist_val}'" if "'" not in dlist_val else f'"{dlist_val}"'
            xpath = f".//*[self::li or self::div][normalize-space()={q}]"
            option_el = menu_el.find_element(By.XPATH, xpath)
            option_el.click()
