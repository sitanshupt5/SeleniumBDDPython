# Created by Sitanshu at 19-09-2025
Feature: Verify navigations for UiCogmento application.
  # Enter feature description here

  @Sample
  Scenario: Verify Login Happy Path
    Given Dataset "HappyPathLogin" is loaded for the scenario
    And I open "Login" page of the application
    When I populate the fields in "Login" page with corresponding data
    And I click on "login_button" on "Login" page
    Then I verify navigation to "Landing" page

  @Sample
  Scenario Outline: Verify Login Error Path: "<Scenario>"
    Given Dataset "<Dataset>" is loaded for the scenario
    And I open "Login" page of the application
    When I populate the fields in "Login" page with corresponding data
    And I click on "login_button" on "Login" page
    Then I verify "error_message_text" text on "Login" page
    Examples:
    |Scenario          | Dataset             |
    |Invalid User Name | InvalidUsernameLogin|
    |Invalid Password  | InvalidPasswordLogin|
    |Without Password  | NullPasswordLogin   |
    |Without User Name | NullUsernameLogin   |