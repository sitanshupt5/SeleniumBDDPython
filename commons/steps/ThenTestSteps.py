from behave import then

from utilities.custom_logger import LogGen
from utilities.read_property import ReadConfig
from utilities.ui_actions import UiActions
from commons.types.context_protocols import TestContext

logger = LogGen.loggen('ThenTestSteps')


@then('I verify that the text: "{expected_page_title}" {assertion_type} matches the current page title')
def verify_the_page_title(context:TestContext, expected_page_title: str, assertion_type: str) -> None:
    current_page_title = context.driver.title
    print(current_page_title)
    if assertion_type == 'exactly':
        assert expected_page_title == current_page_title, (f"Page title does not match "
                                                           f"exactly, Expected: "
                                                           f"{expected_page_title}\t"
                                                           f"Actual: {current_page_title}")
        logger.info(f"Page title matches exactly, Expected: {expected_page_title}\tActual: "
                    f"{current_page_title}")
    elif assertion_type == 'partially':
        assert expected_page_title in current_page_title, (f"Page title does not match "
                                                           f"partially, Expected: "
                                                           f"{expected_page_title}\tActual: "
                                                           f"{current_page_title}")
        logger.info(f"Page title matches partially, Expected: {expected_page_title}\tActual: "
                    f"{current_page_title}")
    else:
        raise ValueError(f"Invalid assertion type: {assertion_type}")


@then('I verify navigation to "{page}" page')
def verify_page_navigation_successful(context: TestContext, page: str) -> None:
    UiActions(context.driver).verify_page_loaded()
    logger.info(f"{page} page load complete")
    UiActions(context.driver).verify_page_url_matches_registry(page=page)
    UiActions(context.driver).verify_page_header_if_present(page=page, wait='present')
    UiActions(context.driver).assert_all_locators_present(page=page)
    logger.info(f"Navigation to {page} page successfully completed")


@then('I verify "{message}" text on "{page_name}" page')
def verify_message_text(context:TestContext, message: str, page_name: str) -> None:
    UiActions(context.driver).assert_message_text_from_dataset(
        page=page_name,
        name=message,
        dataset=getattr(context, "dataset", None),
        dataset_name=getattr(context, "dataset_name", None),
        wait="visible",
        timeout=5,
    )


