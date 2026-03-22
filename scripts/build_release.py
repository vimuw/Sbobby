"""
Unified build/check helper for El Sbobinator.

This is the single entrypoint used by local scripts and CI for:
- dependency installation
- lint/test checks
- WebUI build
- PyInstaller packaging
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WEBUI_DIR = ROOT / "webui"
APP_NAME = "El Sbobinator"
BASE_REQUIREMENTS = ROOT / "requirements.lock"
FALLBACK_REQUIREMENTS = ROOT / "requirements.txt"
DEV_REQUIREMENTS = ROOT / "requirements-dev.txt"
PYTHON_CHECK_TARGETS = [
    "el_sbobinator",
    "tests",
    "scripts",
    "El_Sbobinator.pyw",
    "El_Sbobinator_WebUI.pyw",
    "profile_imports.py",
]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run(cmd: list[str], cwd: Path | None = None) -> None:
    if os.name == "nt" and cmd and cmd[0] == "npm":
        cmd = ["npm.cmd", *cmd[1:]]
    subprocess.run(cmd, cwd=str(cwd or ROOT), check=True)


def _requirements_file() -> Path:
    return BASE_REQUIREMENTS if BASE_REQUIREMENTS.exists() else FALLBACK_REQUIREMENTS


def install_python_dependencies(include_dev: bool = False) -> None:
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "-r", str(_requirements_file())])
    if include_dev and DEV_REQUIREMENTS.exists():
        run([sys.executable, "-m", "pip", "install", "-r", str(DEV_REQUIREMENTS)])


def install_packaging_dependencies(ui: str) -> None:
    packages = ["pyinstaller"]
    if ui == "webui":
        packages.extend(["pywebview", "plyer"])
    run([sys.executable, "-m", "pip", "install", *packages])


def install_node_dependencies(skip_npm_install: bool) -> None:
    if skip_npm_install:
        return
    run(["npm", "install"], cwd=WEBUI_DIR)


def run_python_checks() -> None:
    existing_targets = [str(ROOT / target) for target in PYTHON_CHECK_TARGETS if (ROOT / target).exists()]
    run([sys.executable, "-m", "ruff", "check", *existing_targets])
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"])


def run_webui_checks(skip_npm_install: bool) -> None:
    install_node_dependencies(skip_npm_install=skip_npm_install)
    run(["npm", "run", "lint"], cwd=WEBUI_DIR)
    run(["npm", "test"], cwd=WEBUI_DIR)


def build_webui(skip_npm_install: bool) -> None:
    install_node_dependencies(skip_npm_install=skip_npm_install)
    run(["npm", "run", "build"], cwd=WEBUI_DIR)


def pyinstaller_command(target: str, ui: str) -> list[str]:
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm"]
    if target == "windows":
        command.extend(["--clean", "--onefile", "--windowed"])
    else:
        command.extend(["--windowed"])

    command.extend(
        [
            "--add-data",
            "webui/dist;webui/dist" if os.name == "nt" else "webui/dist:webui/dist",
            "--collect-all",
            "imageio_ffmpeg",
            "--collect-all",
            "keyring",
            "--hidden-import",
            "webview",
            "--hidden-import",
            "clr",
            "--name",
            APP_NAME,
            "El_Sbobinator_WebUI.pyw",
        ]
    )
    return command


def artifact_path(target: str) -> Path:
    if target == "windows":
        return ROOT / "dist" / f"{APP_NAME}.exe"
    return ROOT / "dist" / f"{APP_NAME}.app"


def run_postbuild_smoke(target: str) -> None:
    expected = artifact_path(target)
    if not expected.exists():
        raise FileNotFoundError(f"Artifact mancante dopo la build: {expected}")
    if expected.stat().st_size <= 0:
        raise RuntimeError(f"Artifact vuoto o corrotto: {expected}")
    run([sys.executable, "scripts/smoke_test.py"], cwd=ROOT)


def command_deps(args: argparse.Namespace) -> None:
    install_python_dependencies(include_dev=bool(args.dev))
    install_packaging_dependencies(args.ui)
    if args.ui == "webui":
        install_node_dependencies(skip_npm_install=bool(args.skip_npm_install))


def command_check(args: argparse.Namespace) -> None:
    if not args.skip_python:
        run_python_checks()
    if not args.skip_webui:
        run_webui_checks(skip_npm_install=bool(args.skip_npm_install))


def command_build(args: argparse.Namespace) -> None:
    if args.install_deps:
        install_python_dependencies(include_dev=bool(args.dev_deps))
        install_packaging_dependencies(args.ui)

    if not args.skip_checks:
        run_python_checks()
        if args.ui == "webui":
            run_webui_checks(skip_npm_install=bool(args.skip_npm_install))

    if args.ui == "webui":
        build_webui(skip_npm_install=bool(args.skip_npm_install))

    run(pyinstaller_command(args.target, args.ui), cwd=ROOT)
    if not args.skip_postbuild_smoke:
        run_postbuild_smoke(args.target)


def command_validate(args: argparse.Namespace) -> None:
    from el_sbobinator.validation_service import validate_environment

    result = validate_environment(api_key=args.api_key, validate_api_key=bool(args.check_api_key))
    print(result["summary"])
    for check in result["checks"]:
        status = check["status"].upper()
        label = check["label"]
        message = check["message"]
        details = check.get("details")
        print(f"- [{status}] {label}: {message}")
        if details:
            print(f"  {details}")
    if not result["ok"]:
        raise SystemExit(1)


def command_smoke(args: argparse.Namespace) -> None:
    if args.target:
        run_postbuild_smoke(args.target)
    else:
        run([sys.executable, "scripts/smoke_test.py"], cwd=ROOT)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    deps_parser = subparsers.add_parser("deps", help="Install Python/Node dependencies")
    deps_parser.add_argument("--ui", choices=["webui"], default="webui")
    deps_parser.add_argument("--dev", action="store_true")
    deps_parser.add_argument("--skip-npm-install", action="store_true")
    deps_parser.set_defaults(func=command_deps)

    check_parser = subparsers.add_parser("check", help="Run lint/tests")
    check_parser.add_argument("--skip-python", action="store_true")
    check_parser.add_argument("--skip-webui", action="store_true")
    check_parser.add_argument("--skip-npm-install", action="store_true")
    check_parser.set_defaults(func=command_check)

    build_parser = subparsers.add_parser("build", help="Build the distributable app")
    build_parser.add_argument("--target", choices=["windows", "macos"], required=True)
    build_parser.add_argument("--ui", choices=["webui"], default="webui")
    build_parser.add_argument("--install-deps", action="store_true")
    build_parser.add_argument("--dev-deps", action="store_true")
    build_parser.add_argument("--skip-npm-install", action="store_true")
    build_parser.add_argument("--skip-checks", action="store_true")
    build_parser.add_argument("--skip-postbuild-smoke", action="store_true")
    build_parser.set_defaults(func=command_build)

    validate_parser = subparsers.add_parser("validate", help="Validate local environment and optional API access")
    validate_parser.add_argument("--api-key", default="")
    validate_parser.add_argument("--check-api-key", action="store_true")
    validate_parser.set_defaults(func=command_validate)

    smoke_parser = subparsers.add_parser("smoke", help="Run smoke tests and optional post-build artifact checks")
    smoke_parser.add_argument("--target", choices=["windows", "macos"])
    smoke_parser.set_defaults(func=command_smoke)

    return parser


def main(argv: list[str] | None = None) -> None:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    if effective_argv and effective_argv[0].startswith("-"):
        effective_argv.insert(0, "build")

    parser = build_parser()
    args = parser.parse_args(effective_argv)
    args.func(args)


if __name__ == "__main__":
    main()
