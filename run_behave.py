import os
import sys
import shutil
import subprocess
from pathlib import Path
from behave.__main__ import main as behave_main
from datetime import datetime


def _parse_cli():
    import argparse
    p = argparse.ArgumentParser(description="Behave multi-app runner")
    p.add_argument("--app", default=os.environ.get("APP_NAME") or "application",
                   help="App folder name (e.g., application, application2)")
    p.add_argument("--tags", default=os.environ.get("TAGS"),
                   help="Behave tag expression, e.g., @smoke and not @wip")
    p.add_argument("--env", dest="cur_env", default=os.environ.get("ENV") or "dev",
                   help="Environment name to export if you use it in config")
    p.add_argument("--headless", choices=["true", "false"],
                   help="Run browser headless (true/false). If omitted defaults to "
                        "config.ini value")
    return p.parse_known_args()


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _features_dir(cur_dir: str | None) -> Path:
    root = _project_root()
    app = cur_dir or "application"  # default app if not provided
    return (root / app / "features").resolve()


def _results_dir(app: str) -> Path:
    d = _project_root() / "reports" / app / "allure-results"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _report_dir(app: str) -> Path:
    d = _project_root() / "reports" / app / "allure-report"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _normalize_tags(tags: str) -> str:
    tokens = []
    for tok in tags.split():
        if tok.lower() in {"and", "or", "not", "(", ")"}:
            tokens.append(tok)
        else:
            tokens.append(tok if tok.startswith("@") else f"@{tok}")
    return " ".join(tokens)


def run_tests(tags: str | None = None, cur_dir: str | None = None, cur_env: str | None =
                                                    None, headless: str | None = None) -> int:
    os.chdir(_project_root())
    app = cur_dir or "application"
    os.environ["APP_NAME"] = app
    os.environ["APP_DIR"] = str(_project_root() / app)
    results = _results_dir(app)
    feats = _features_dir(app)
    args = [
        "-f", "allure_behave.formatter:AllureFormatter", "-o", str(results),
        "--no-capture",
        "--no-logcapture",
        str(feats),
    ]
    if tags:
        expr = _normalize_tags(tags)
        args.append(f"--tags={expr}")
        os.environ["tags"] = expr
    if cur_dir:
        os.environ["dir"] = cur_dir
    if cur_env:
        os.environ["env"] = cur_env
    if headless is not None:
        args += ["-D", f"headless={headless.lower()}"]

    return behave_main(args)


def generate_allure_report(app: str) -> None:
    results = str(_results_dir(app))
    report = str(_report_dir(app))
    allure = shutil.which("allure")
    if not allure:
        print("Allure CLI not found on PATH.\n"
              "Install it, then run:\n"
              f"  allure generate {results} --clean -o {report}\n"
              "Windows: choco install allure\n"
              "macOS:   brew install allure")
        return
    cmd = [allure, "generate", results, "--clean", "-o", report]
    print("Generating Allure HTML:", " ".join(cmd))
    subprocess.run(cmd, check=False)


if __name__ == "__main__":
    args, passthru = _parse_cli()
    RUN_ID = datetime.now().strftime("%Y%m%d-%H%M%S")

    # If CLI args not provided, use defaults
    app = args.app or "application"
    tags = args.tags or "@Sample"
    env = args.cur_env or "qa"
    headless = args.headless

    # Export for environment.py + locator_registry
    os.environ["RUN_ID"] = RUN_ID
    os.environ["APP_NAME"] = app
    os.environ["APP_DIR"] = str(_project_root() / app)
    if tags:
        os.environ["TAGS"] = tags
    if env:
        os.environ["ENV"] = env

    print(f"RUN_ID={RUN_ID} APP={app} TAGS={tags or ''} ENV={env} HEADLESS={headless or 'unset'}")
    exit_code = run_tests(tags=tags, cur_dir=app, cur_env=env, headless=headless)
    generate_allure_report(app)
    sys.exit(exit_code)
