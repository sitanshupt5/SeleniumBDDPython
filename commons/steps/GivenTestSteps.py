from behave import given

from utilities.custom_logger import LogGen
from utilities.data_registry import extract_dataset, DataError
from utilities.read_property import ReadConfig
from utilities.ui_actions import UiActions
from commons.types.context_protocols import TestContext

logger = LogGen.loggen('GivenTestSteps')


@given('I open "{page}" page of the application')
def open_application_page(context, page: str) -> None:
    """
    Open the application page whose URL is configured as `page_url` in the page YAML.
    """
    UiActions(context.driver).open_page(page, wait_for="load")


@given('Dataset "{dataset_name}" is loaded for the scenario')
def step_load_dataset(context: TestContext, dataset_name: str) -> None:
    """
    Load a named dataset from the feature's data file (already parsed in before_feature)
    and store it on context.dataset for subsequent steps.

    :param context: Behave context.
    :param dataset_name: Top-level key in <feature>_data.yml corresponding to this scenario.
    :raises AssertionError: If data file wasn't preloaded or dataset is missing.
    """
    if not hasattr(context, "data_file_content") or context.data_file_content is None:
        raise AssertionError(
            "Data file was not loaded. Ensure 'before_feature' loads data_file_content."
        )
    try:
        context.dataset = extract_dataset(context.data_file_content, dataset_name)
        context.dataset_name = dataset_name
        logger.info(f"Dataset {dataset_name} loaded successfully for the scenario")
    except DataError as exc:
        raise AssertionError(str(exc))
