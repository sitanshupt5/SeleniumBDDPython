# Selenium Behave Python Test Framework

A Python-based BDD test automation framework for UI testing, built on **Selenium 4**, **Behave**, and **Allure Reports**. Page objects and test data are defined in YAML, keeping locator and data management fully separate from test logic.

---

## Project Structure

```
SeleniumBehavePython/
│
├── application/                            # Test application (one per app under test)
│   ├── data/                               # Test data, one YAML file per feature
│   │   └── <feature_name>_data.yml
│   ├── features/                           # BDD feature files and hooks
│   │   ├── environment.py                  # Behave lifecycle hooks (WebDriver setup/teardown, Allure artifacts)
│   │   ├── <feature_name>.feature
│   │   └──steps/
│   │      └── common_steps.py              # Re-exports all steps from commons/steps/
│   └── pages/                              # Page Object definitions (YAML)
│       └── <page_name>_page.yml
│
├── commons/                                # Shared step definitions and type contracts
│   ├── steps/
│   │   ├── GivenTestSteps.py               # @given step implementations
│   │   ├── WhenTestSteps.py                # @when step implementations
│   │   └── ThenTestSteps.py                # @then step implementations
│   └── types/
│       └── context_protocols.py            # Typed protocol for the Behave context object
│
├── utilities/                              # Core framework utilities
│   ├── ui_actions.py                       # Selenium interaction API (click, type, wait, verify)
│   ├── locator_registry.py                 # Loads YAML pages, resolves locators with fallback
│   ├── data_registry.py                    # Loads YAML data, maps keys to form fields
│   ├── read_property.py                    # Reads configuration from config.ini
│   ├── custom_registry.py                  # Colored console and file logger
│   └── allure_helpers.py                   # Allure attachment helpers
│
├── configuration/
│   └── config.ini                          # Environment URLs, wait times, headless toggle
│
├── reports/                                # Generated at runtime
│   └── <app>/
│       ├── allure-results/
│       └── allure-report/
│
├── logs/                                   # Log files per RUN_ID
├── behave.ini                              # Behave defaults (tag exclusions, output settings)
└── run_behave.py                           # Main test runner entry point
```

---

## Running Tests

**Pre-Requisites:** install dependencies and ensure ChromeDriver/Geckodriver is on PATH.

```bash
pip install -r requirements.txt
```

**Run Tests:**

```bash
# Run all @Sample scenarios (default if no tag provided)
python run_behave.py --app application --tags "@Sample"

# Run  a specific tag
python run_behave.py --tags "@CreateContact"

# Combine tags
python run_behave.py --tags "@Sample and not @wip"

# Run headless
python run_behave.py --headless true --tags "@Sample"

# Run against a specific environment
python run_behave.py --app application --env qa
```

| Argument | Default| Description |
|---|---|---|
|`--app` | `application` | App folder name under the project root |
|`--tags` | `@Sample` | Behave tag expression |
| `--env` | `dev` | Environment name (`qa`/ `dev`), sets the base URL |
| `--headless` | config.ini value | `true`/ `false`, overrides config.ini |

After a run , Allure HTML reports are generated automatically under `reports/<app>/allure-report/`.

**Generate Allure Report Manually:**

```bash
allure generate reports/application/allure-results --clean -o reports/application/allure-report
allure open reports/application/allure-report
```

---
## Flow of a Test

The following sequence describes what happens from the moment `run_behave.py` is invoked to the final Allure report.

```
run_behave.py
    │
    ├── Sets env vars: RUN_ID, APP_NAME, APP_DIR, TAGS, ENV
    ├── Calls behave_main() with AllureFormatter and --tags
    │
    └── Behave lifecycle (environment.py hooks)
         │ 
         ├── before_all()
         │      Sets up reports/ directory.
         │      Reads base url from config.ini
         │
         ├── before_feature()
         │      Locates <feature>_data.yml via data_registry.get_data_file().
         │      Parses and stores it in context.data_file_content.
         │
         ├── before_scenario()
         │      Creates Chrome or Firefox Webdriver (headless if configured).
         │      Attaches driver to context.driver.
         │
         ├── before_step() → Logs the step text 
         │
         ├── [Step executes - see Step execution below]
         │
         ├── after_step()
         │      Attaches current URL + screenshot to Allure for every step.
         │      Attaches page source on failure.
         │
         ├── after_scenario() 
         │      Attaches final screenshot to Allure.
         │      Saves failure screenshot to disk (reports/<app>/<scenario>_<ts>.png
         │      Quits Webdriver
         │
         └── after_all() → logs run complete 
```

### Step Execution

Each Gherkin step maps to a Python function in `commons/steps/`:

```
Given Dataset "HappyPathLogin" is loaded for the scenario
    └── GivenTestSteps.py: extract_dataset() → context.dataset
    
And I open "Login" page of the application
    └── GivenTestSteps.py: UiActions.open_page("Login")
        └── locator_registry.page_url("Login") → navigates to YAML page_url

When I populate the fields in "Login" page with corresponding data
    └── WhenTestSteps.py: data_registry.map_data_to_fields(actions, "Login", context.dataset)
        └── Iterates dataset keys matching page "login":
                login_username_input → type_text(page, "username", value)
                login_password_input → type_text(page, "password", value)

And I click on "login_button" on "Login" page
    └── WhenTestSteps.py: UiActions.find_element("Login", "login_button").click()
        └── locator_registry.locate tries each candidate locator in YAML order

Then I verify navigation to "Landing" page
    └── ThenTestSteps.py:   UiActions.verify_page_url_matches_registry("Landing")
                            UiActions.verify_page_header_if_present("Landing")
                            UiActions.assert_all_locators_present("Landing")
```

---

## Test Case Creation

### 1. Define the Page Object (YAML)

Create `application/pages/<page_name>_page.yml`. The top-level key is the  **page name** used in all step sentences.

```yaml
MyPage:
  page_url: "https://example.com/my-page"
  page_title: "My Page Title"               # optional; verified by "I verify navigation to" step
  url_regex: "example\\.com/my-page"        # optional; used instead of exact url match
  locators:
    some_input:
      - "xpath, //input[@id='some-input']"
      - "css, input#some-input"             # fallback tried if first locator fails
    submit_button:
      - "xpath, //button[text()='Submit']"
    result_message:
      - "xpath, //div[@class='result']"
```

Mark locators that should be verified on page load appending `, page_load_check`:

```yaml
    page_header:
      - "xpath, //h1[@class='header'], page_load_check"
```

### 2. Create the Test Data File (YAML):

Create `application/data/<feature_name>_data.yml`. Each top-level key is a **dataset name** passed to the `Dataset` step. Keys inside each dataset follow the naming convention `<page>_<field>_<type>` (see Standardizations)

```yaml
MyScenarioDataset:
  mypage_some_input_input: "Hello World"
  mypage_assert_result_message: "Success"
```

### 3. Write the Feature File

Create `application/features/<feature_name>.feature`.

```gherkin
Feature: Verify My Page functionality.

    @MyTag
    Scenario: Verify successfull submission
        Given Dataset "MyScenarioDataset" is loaded for the scenario
        And I open "MyPage" page of the application
        When I populate the fields in "MyPage" page with corresponding data
        And I click on "submit_button" on "MyPage" page
        Then I verify navigation to "ResultPage" page
        And I verify "result_message" text on "ResultPage" page
    
    @MyTag
    Scenario Outline: Verify submission with <Scenario>
        Given Dataset "<Dataset>" is loaded for the scenario
        And I open "MyPage" page of the application
        When I populate the fields in "MyPage" page with corresponding data
        And I click on "submit_button" on "MyPage" page
        Then I verify navigation to "ResultPage" page
        And I verify "result_message" text on "ResultPage" page
        Examples:
        | Scenario          | Dataset               |
        | valid input       | ValidInputData        |
        | invalid input     | InvalidInputData      |
```

### 4. Available Step Sentences

#### Given

| Step | Description |
|---|---|
|`Given Dataset "{name}" is loaded for the scenario`| Loads a named dataset from the feature's data YAML into `context.dataset` |
|`Given I open "{page}" page of the application`| Navigates to the `page_url` defined in the page YAML |

#### When

| Step | Description |
|---|---|
| `When I populate the fields in "{page}" page with corresponding data` | Bulk-populates all fields on the page using `context.dataset`|
| `When I enter text "{text}" in "{element}" field on "{page}" page`    | Types text into a specific element |
| `When I click on "{element}" on "{page}" page`| Clicks a specific element |
| `When I navigate to "{page_name}" page using "{option}" option`| Navigates via `sidebar` (hover + click) or `page_url` (direct URL)|
| `When I switch to "{iframe_locator}" overlay on "{page_name}" page`| Switches Selenium context into an iframe |
| `When I switch to parent frame` | Switches to the parent frame |
| `When I switch to default content` | Exits all iframes back to main document |
| `When I navigate back on the browser` | Browser back navigation |
| `When I navigate forward on the browser`| Browser forward navigation |

#### Then

| Step | Description |
|---|---|
| `Then I verify navigation to "{page}" page` | Verifies URL, page header and all `page_load_check` locators |
| `Then I verify "{message}" text on "{page_name}" page` | Verifies element text against `assert_<message>` value in dataset |
| `Then I verify that the text: "{expected}" {type} matches the current page title` | Verifies page title; `type` is `exactly` or `partially` |

---

## Standardizations

### Data Key Naming Convention

All keys in `*_data.yml` files follow the strict format:

```
<page_name>_<field_name>_<field_type>
```

- **`page_name`** - Lowercase version of the YAML page key with spaces removed (eg. `Login` → `login`, `CreateNewContact` → `createnewcontact`).
- **`field_name`** - Exact locator key from the page YAML (can contain underscores)
- **`field_type`** - One of the supported types below.

### Supported Field Types

| Type | Value    | Behavior |
|---|---|---|
| `input`| `string` | Clears the field and types the value |
| `checkbox` | `bool` | Checks or unchecks the checkbox to match the target state |
| `radio` | `bool` | Clicks `<field>_true` or `<field>_false` locator |
| `selectvalue` | `string` | Selects `<option value="...">` in a native `<select>` |
| `selectindex` | `int` | Selects by 0-based index in a native `<select>` |
| `selecttext`  | `string` | Selects by visible text in a native `<select>` |
| `dbutton` | `bool` | Custom dropdown opener - `True` = click to open |
| `dlist` | `string` | Custom dropdown option text to select |
| `assert` | `string` | Expected text verified by the `I verify "{message}" text` step; skipped during field population |

**Custom dropdown pairing (`dbutton` + `dlist`):** Both keys must be present for the same dropdown base. The `dlist` key must end with `_menu`

**Field Type `button`:** button is also a field type but does not require passing of data to be interacted with. You can directly interact with a button element using the `When I click on "{element}" on "{page}" page`.

```yaml
# Correct pairing for a "status" dropdown:
mypage_status_dropdown_dbutton: True
mypage_status_dropdown_menu_dlist: "Active"
```

Corresponding locator keys in the page YAML:

```yaml
MyPage:
  locators:
    status_dropdown:                            # opener - matches dbutton field_name
      - "xpath, //div[@id='status-trigger']"
    status_dropdown_menu:                       # menu container - must end with menu
      - "xpath, //div[@id='status-menu']"
```

### Page YAML Conventions

- Top-level key = page name. Must be **PascalCase** and match exactly what is passed in the step sentences.
- Locator format: `"<strategy>, <selector>"` - strategy and selector separated by a comma.
- Supported strategies: `xpath`, `css`, `id`, `name`, `tag`, `link_text`, `partial_link_text`.
- Multiple locators per element listed as a YAML sequence; they are tried in order with automatic fallback.
- Append `, page_load_check` to any locator that should be verified by the `I verify navigation to` step.

### Tagging Conventions
| Tag | Purpose |
|---|---|
| `@wip` | Work in progress - excluded from all runs by default (see `behave.ini`) |
| `@Sample` | Smoke/sample scenarios included in default runs |
| Feature-specific tags (e.g., `@CreateContact`) | Used to target a specific feature or scenario group |

### Assertion Keys in Data Files

Assertion values used by the `I verify "{message}" text` step must include `assert` in the field name segment:

```yaml
mypage_assert_error_message_text: "Expected error text"
```

The `message` parameter in the step (`"error_message_text"`) maps directly to the locator key in the page YAML. The expected text is read from `<page>_assert_<message>` in the dataset.

### Configuration

`configuration/config.ini` controls runtime behavior:

```ini
[environment]
type = qa                       # Default environment

[common_info]
qa_baseURL = https://...
dev_baseURL = https://...

[wait]
sec10 = 10
sec5 = 5

[driver_configuration]
headless = false                # Override with --headless true at runtime
```

---

## CI/CD Setup (Bitbucket Pipelines + AWS)

This section walks through setting up automated test execution on Bitbucket  Pipelines with reports
hosted on AWS S3. Follow the steps in order ─ each section builds on the previous one.

---

### Pre-Requisites

You need the following before running any pipeline.

#### 1. AWS Account

You need an AWS account and an IAM user with permission to create the infrastructure.

**Create an IAM user:**
1. Log in to the [AWS Console](https://console.aws.amazon.com)
2. Got to **IAM** → **Users** → **Create user**
3. Give it a name (e.g. `bitbucket-bootstrap`)
4. On the **Permissions** page, choose **Attach policies directly**
5. Attach these managed policies:
   - `IAMFullAccess`
   - `AmazonS3FullAccess`
   - `AWSCloudFormationFullAccess`
6. Finish creating the user
7. Go to the user → **Security credentials** → **Create access key**
8. Choose **Other** → create → **download or copy both values**:
   - Access key ID
   - Secret access key

> These values are used only during the one-time Bootstrap step. You can delete them from Bitbucket after Bootstrap is complete.

#### 2. Bitbucket Workspace Slug and UUID

You need two identifiers for your Bitbucket workspace:

**Workspace slug** ─ visible in the URL when you are in your workspace:
```
https://bitbucket.org/{WORKSPACE_SLUG}/
```

**Workspace UUID** ─ found in Bitbucket settings:
1. Go to your Bitbucket workspace
2. Click **Settings** (bottom of the left sidebar)
3. Click **Workspace details**
4. Copy the **Workspace UUID** (looks like `{39c79d5f-e07d-4bc0-9107-bf39b0c24f41}`, including the curly braces)

#### 3. Your Repository Slug

The repo slug is the last part of your repository URL:
```
https://bitbucket.org/{workspace}/{REPO_SLUG}/
```

---

### Step 1 ─ Fill in the Config File

Open `configuration/pipeline-config.env` and replace every placeholder with your real values.

```
WORKSPACE_SLUG      → Your Bitbucket workspace slug
WORKSPACE_UUID      → Your Bitbucket workspace UUID (with curly braces)
REPO_SLUG           → Your Bitbucket repository slug
AWS_REGION          → The AWS region you want to deploy to (e.g. ap-south-1)
S3_BUCKET_NAME      → A unique name for your S3 bucket (e.g. mycompany-allure-reports)
STACK_PREFIX        → A short prefix for your AWS resource names
```

**S3 bucket name rules:** lowercase letters, numbers and hyphens only. No spaces or underscores.
Must be globally unique ─ if the name is already taken by any other AWS account, Bootstrap will fail.
Add something specific like your company name to make it unique.

---

### Step 2 ─ Set BitBucket Repository Variables

Repository variables are like a secure notepad inside Bitbucket. Sensitive values like AWS keys
go here ─ never in files that are commited to the repository.

**How to add repository variables:**
1. Go to your Bitbucket repository
2. Click **Repository settings** (bottom of the left sidebar)
3. Click **Repository variables** (under Pipelines)
4. For each variable below, click **Add variable**, enter the Name and Value, and click **Add**

**Variables to add before Bootstrap:**

| Name | Value | Secured? |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | Your IAM access key ID | Yes (tick the checkbox) |
| `AWS_SECRET_ACCESS_KEY` | Your IAM secret access key | Yes (tick the checkbox) |
| `AWS_DEFAULT_REGION` | Your AWS region (e.g. `ap-south-1`) | No |

> Ticking **Secured** hides the value from logs and from other users.

---

### Step 3 ─ Run the Bootstrap Pipeline

The Bootstrap pipeline create all AWS infrastructure and upload the report portal.
It only need to be run once.

**How to trigger it:**
1. Go to your Bitbucket repository
2. Click **Pipelines** in the left sidebar
3. Click **Run pipeline** (top right)
4. Under **Pipeline**, select **Bootstrap**
5. Click **Run**

The pipeline will:
- Deploy 3 AWS CloudFormation stacks (OIDC provider, IAM role, S3 bucket)
- Upload the report portal website to your S3 bucket
- Print your **Role ARN** and **Portal URL** at the end of the log

**At the end of the Bootstrap log, look for this section:**
```
================================================================
BOOTSTRAP COMPLETE
ACTION REQUIRED ─ Save this as a Bitbucket repository variable:
  Name : BITBUCKET_AWS_ROLE_ARN
  Value: arn:aws:iam::123456789012:role/myproject-bitbucket-oidc-role

Your report portal URL (bookmark this):
  http://mycompany-allure-reports.s3-website-ap-south-1.amazonaws.com
================================================================
```

---

### Step 4 ─ Save the Role ARN

1. Copy the **Value** shown next to ` BITBUCKET_AWS_ROLE_ARN` in the Bootstrap log
2. Go back to **Repository settings** → **Repository variables**
3. Add a new variable:

| Name | Value | Secured? |
|---|---|---|
| `BITBUCKET_AWS_ROLE_ARN` | The ARN you just copied | Yes |

After this step, the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` variable are no longer needed
and can be deleted from Repository variables.

---

### Step 5 ─ Bookmark the Portal URL

Copy the URL printed under **"Your report portal URL"** in the Bootstrap log and bookmark it in
your browser. This is where all test reports will be published.

---

### Running Tests

Once Bootstrap is complete, you can run tests any time using the **Run-Tests** pipeline.

**How to trigger it:**
1. Go to **Pipelines** → **Run pipeline**
2. Select **Run-Tests**
3. Fill in the parameters (or leave them at their defaults):

| Parameter | Default | What it means |
|---|---|---|
| `APP` | `application` | The app folder to test. Must match a folder name in the repository root (e.g. `application`) |
| `ENV` | `qa` | The environment to test against. `qa` and `dev` are configured in `configuration/config.ini`. |
| `TAGS` | `@Sample` | Which test scenarios to run. Must match a tag from a `.feature` file (e.g. `@CreateContact`, `@Sample`). |

**Finding available tags:**
Open any `.feature` file under `application/features/`. Tags appear above `Scenario:` lines,
starting with `@`:
```gherkin
@CreateContact
Scenario: Create a new contact
```

4. Click **Run**

The pipeline will run the tests, generate the Allure report and upload it to S3 under:
```
APP / YYYY-MM-DD / BUILD_NUMBER /
```
The build number matches the pipeline run number shown in Bitbucket.

---

### Viewing Reports

1. Open the portal URL you bookmarked in Step 5
2. You will see a list of app directories (e.g. `application/`)
3. Click oan app directory to see a list of dates
4. Click a data to see a list of pipeline build numbers
5. Click a build number to open the fill Allure report directly

**Understanding the Allure report:**
- **Overview**  ─ total pass/fail count and pie char for this run
- **Trend**     ─ pass/fail history across multiple runs (appears from the second run onward)
- **Suites**    ─ breakdown by scenario and feature file
- **Timeline**  ─ time taken per scenario
- Click any failed scenario to see the step that failed, screenshot and error message

---

### Re-Deploying Infrastructure

If you ever change ` pipeline-config.env` or the CloudFormation templates, run the **Deploy-Infra**
pipeline to apply the changes. This uses OIDC (no static keys needed).

---

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Bootstrap fails: `AWS_ACCESS_KEY_ID not set` | Repo variable not added | Add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` is Repository variables |
| Run-Tests fails: `BITBUCKET_AWS_ROLE_ARN not set` | Step 4 not completed | Copy the role ARN from the Boostrap log and add it as a repo variable |
| Run-Tests fails at OIDC step with `AccessDenied` | Role ARN is wornd or repo/workspace mismatch | Re-check that `WORKSPACE_SLUG`, `WORKSPACE_UUID` and `REPO_SLUG` in `pipeline-config.env` are correct, then re-run Bootstrap |
| Portal URL shows blank page or XML | Bootstrap did not upload the webApp | Re-run the Bootstrap pipeline |
| Trend graphs not showing | Expected on first run ─ not history exists yet | Run tests a second time; trends appear from run 2 onward |
| App directory not visible in portal | No test run has been completed for that app yet | Run the Run-Tests pipeline with the correct `APP` value |
| S3 bucket name already taken | Another AWS account owns that name | Choose a more unique name in `pipeline-config.env` and re-run Bootstrap |



