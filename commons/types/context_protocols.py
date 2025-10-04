# Python 3.9+
from typing import Protocol, Optional, Dict, Any, runtime_checkable
from selenium.webdriver.remote.webdriver import WebDriver

@runtime_checkable
class HasDriver(Protocol):
    """Context has a Selenium WebDriver."""
    driver: WebDriver

@runtime_checkable
class HasArtifacts(Protocol):
    """Context has common artifact directories."""
    project_root: str
    reports_dir: str
    download_dir: str

@runtime_checkable
class HasConfig(Protocol):
    """Context has configuration values."""
    base_url: str  # you can set this in hooks from your config

@runtime_checkable
class HasData(Protocol):
    """Context can carry arbitrary test data."""
    data: Dict[str, Any]  # optional “stash” for scenarios
    data_file_content: Dict[str, Dict[str, Any]]
    dataset: Dict[str, Any]

class TestContext(HasDriver, HasArtifacts, HasConfig, HasData, Protocol):
    """Full test context shape used in steps."""
    # Add more typed attributes here as your framework grows:
    # api_token: Optional[str]
    # timeout_sec: int
    # current_user: Optional[str]
    pass
