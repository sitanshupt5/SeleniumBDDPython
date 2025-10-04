from behave import when
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from utilities import utils
from utilities.custom_logger import LogGen
from utilities.data_registry import map_data_to_fields
from utilities.locator_registry import locate, page_url
from utilities.ui_actions import UiActions
from commons.types.context_protocols import TestContext

logger = LogGen.loggen('WhenTestSteps')


@when('I enter text "{text}" in "{element}" field on "{page}" page')
def step_enter_text(context: TestContext, text: str, element: str, page: str) -> None:
    """
    Enter text into an input field defined by a Page Object locator.

    :param context: Behave context.
    :param text: Text to type.
    :param element: Locator variable name on the Page Object class.
    :param page: Page Object class name (e.g., "LoginPage").
    :returns: None
    """
    logger.info(f'Enter "{text}" in element "{element}" on page "{page}"')
    ele = UiActions(context.driver).wait_for_element_present(page=page,
                                                             name=element).find_element(page=page, name=element)
    assert ele is not None, f"{element} not found on {page}"
    ele.clear()
    ele.send_keys(text)


@when('I click on "{element}" on "{page}" page')
def step_click_element(context: TestContext, element: str, page: str) -> None:
    """
    Click a UI element defined by a Page Object locator.

    :param context: Behave context.
    :param element: Locator variable name on the Page Object class.
    :param page: Page Object class name.
    :returns: None
    """
    logger.info(f"Click element {element} on page {page}")
    ele = UiActions(context.driver).wait_for_element_clickable(page=page,
                                                             name=element).find_element(page=page, name=element)
    assert ele is not None, f"{element} not found on {page}"
    ele.click()


@when('I verify the label as "{expected_text}" of "{element}" on "{page}" page')
def verify_label(context: TestContext, expected_text: str, element: str, page: str) -> None:
    logger.info(f"Verify label as {expected_text} fr element {element} on {page} page")
    ele = UiActions(context.driver).wait_for_element_present(page=page,
                                                             name=element).find_element(page=page, name=element)
    assert ele.text == expected_text


@when('I get text of all element "{element}" on "{page}" page')
def get_text_all(context: TestContext, element: str, page: str) -> None:
    logger.info('Getting text of all elements')
    elements = UiActions(context.driver).wait_for_element_present(page,
                                                                  element).find_all_elements(page, element)
    for ele in elements:
        print(ele.text)


@when('I navigate back on the browser')
def navigate_back(context: TestContext) -> None:
    logger.info('Navigating back on the browser')
    UiActions(context.driver).navigate_back()


@when('I navigate forward on the browser')
def navigate_forward(context: TestContext) -> None:
    logger.info('Navigating forward on the browser')
    UiActions(context.driver).navigate_forward()


@when('I switch to "{iframe_locator}" overlay on "{page_name}" page')
def step_switch_to_iframe(context: TestContext, iframe_locator: str, page_name: str) -> None:
    """
    Switch the Selenium driver's context into an <iframe> defined in the page YAML.

    The locator name (iframe_locator) must exist under the given page's `locators` block.
    Example YAML:
      SomePage:
        locators:
          details_iframe:
            - css: iframe#iframe-id
            - xpath: //iframe[@title="Details"]

    :param context: Behave context carrying the Selenium driver.
    :param iframe_locator: Locator key of the iframe in the page YAML (e.g., "details_iframe").
    :param page_name: Page block identifier in the YAML (e.g., "SomePage").
    :raises TimeoutException / AssertionError: If the iframe cannot be located/switched to within timeout.
    """
    UiActions(context.driver).switch_to_frame(page=page_name, name=iframe_locator)


@when("I switch to parent frame")
def step_switch_to_parent_frame(context: TestContext) -> None:
    """
    Switch to the immediate parent frame of the current frame.
    """
    UiActions(context.driver).switch_to_parent_frame()


@when("I switch to default content")
def step_switch_to_default_content(context: TestContext) -> None:
    """
    Switch back to the top-level (default) document context (i.e., exit all iframes).
    """
    UiActions(context.driver).switch_to_default_content()


@when('I populate the fields in "{page}" page with corresponding data')
def step_populate_fields(context, page):
    map_data_to_fields(UiActions(context.driver), page, context.dataset)


@when('I navigate to "{page_name}" page using "{option}" option')
def i_navigate_to_page_using_option(context: TestContext, page_name: str, option: str) -> None:
    """
    Navigate to a page either via the persistent sidebar or by using the canonical page_url.

    Conventions:
      - page_name == YAML page block key (e.g., "Login", "Home", "CreateNewContacts", "Landing")
      - sidebar locator key: "sidebar"
      - menu item locator key: page_name.lower() + "_button" (e.g., "createnewcontacts_button")

    :param context: Behave TestContext object.
    :param page_name: Name of the page to navigated to.
    :param option: Method to be used to navigate to the concerned page.
    """
    opt = option.strip().lower()

    if opt == "sidebar":
        sidebar = locate(driver=context.driver, page=page_name, name='sidebar',
                         wait='visible', timeout=10)
        banner = locate(driver=context.driver, page=page_name, name='banner',
                         wait='visible', timeout=10)
        ActionChains(context.driver).move_to_element(sidebar).perform()

        key = f"{page_name.lower()}_button"
        locate(driver=context.driver, page=page_name, name=key,
                         wait='clickable', timeout=10).click()

        ActionChains(context.driver).move_to_element(banner).perform()
        try:
            UiActions(context.driver).verify_page_url_matches_registry(page=page_name)
        except KeyError:
            pass

    elif opt == 'page_url':
        UiActions(context.driver).open_url(url=page_url(page_name))
    else:
        raise AssertionError(f"Unsupported option '{option}'. User 'sidebar' or 'page_url'")

