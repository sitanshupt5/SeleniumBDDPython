# Created by Sitanshu at 23-09-2025
Feature: Validate the Create Contact Flow.
  # Enter feature description here

  @Sample @CreateContact
  Scenario Outline: Create contact with <Scenario>
    Given Dataset "<Dataset>" is loaded for the scenario
    And I open "Login" page of the application
    When I populate the fields in "Login" page with corresponding data
    And I click on "login_button" on "Login" page
    Then I verify navigation to "Landing" page
    When I navigate to "CreateNewContact" page using "sidebar" option
    Then I verify navigation to "CreateNewContact" page
    When I populate the fields in "CreateNewContact" page with corresponding data
    And I click on "save_button" on "CreateNewContact" page
    Then I verify navigation to "ContactDetails" page
    And I verify "email" text on "ContactDetails" page
    When I navigate to "Contacts" page using "sidebar" option
    And I populate the fields in "Contacts" page with corresponding data
    And I click on "commit_button" on "Contacts" page
    And I click on "confirmation_accept_button" on "Contacts" page
    Then I verify navigation to "Contacts" page
    And I verify "no_content_message" text on "Contacts" page
    Examples:
    |Scenario                    |Dataset              |
    |only mandatory field details|MandatoryFieldDetails|
    |all details                 |AllFieldDetails      |