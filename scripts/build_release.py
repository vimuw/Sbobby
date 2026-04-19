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
import shutil
import subprocess
import sys
from pathlib import Path

if os.name == "nt":
    import winreg


ROOT = Path(__file__).resolve().parent.parent
WEBUI_DIR = ROOT / "webui"
PACKAGING_DIR = ROOT / "packaging"
LAUNCHERS_DIR = ROOT / "launchers"
TOOLS_DIR = ROOT / "tools"
REQUIREMENTS_DIR = ROOT / "requirements"
WEBVIEW_ENTRYPOINT = LAUNCHERS_DIR / "El_Sbobinator_WebUI.pyw"
PROFILE_IMPORTS_SCRIPT = TOOLS_DIR / "profile_imports.py"
APP_NAME = "El Sbobinator"
REQUIRED_NODE_MAJOR = 24
BASE_REQUIREMENTS = REQUIREMENTS_DIR / "requirements.lock"
FALLBACK_REQUIREMENTS = REQUIREMENTS_DIR / "requirements.txt"
DEV_REQUIREMENTS = REQUIREMENTS_DIR / "requirements-dev.txt"
PYTHON_CHECK_TARGETS = [
    "el_sbobinator",
    "tests",
    "scripts",
    str(WEBVIEW_ENTRYPOINT.relative_to(ROOT)),
    str(PROFILE_IMPORTS_SCRIPT.relative_to(ROOT)),
]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run(cmd: list[str], cwd: Path | None = None) -> None:
    if os.name == "nt" and cmd and cmd[0] == "npm":
        cmd = ["npm.cmd", *cmd[1:]]
    subprocess.run(cmd, cwd=str(cwd or ROOT), check=True)


def ensure_supported_node_version() -> None:
    result = subprocess.run(
        ["node", "--version"],
        cwd=str(ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    version = result.stdout.strip() or result.stderr.strip()
    normalized = version[1:] if version.startswith("v") else version
    major_text = normalized.split(".", 1)[0]
    try:
        major = int(major_text)
    except ValueError as exc:
        raise RuntimeError(
            f"Versione Node.js non riconosciuta: {version!r}. Richiesta: {REQUIRED_NODE_MAJOR}.x"
        ) from exc

    if major != REQUIRED_NODE_MAJOR:
        raise RuntimeError(
            f"Node.js {REQUIRED_NODE_MAJOR}.x richiesto per la WebUI; rilevato {version}."
        )


def get_windows_webview2_runtime_version() -> str | None:
    if os.name != "nt":
        return None

    registry_paths = (
        (
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        ),
    )

    for root, path in registry_paths:
        try:
            with winreg.OpenKey(root, path) as key:
                value, _ = winreg.QueryValueEx(key, "pv")
                version = str(value).strip()
                if version:
                    return version
        except OSError:
            continue

    return None


def print_windows_webview2_notice(target: str, ui: str) -> None:
    if target != "windows" or ui != "webui":
        return

    version = get_windows_webview2_runtime_version()
    download_url = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

    print()
    print("=== Controllo prerequisito WebView2 ===")
    if version:
        print(f"[OK] WebView2 Runtime rilevato: {version}")
    else:
        print("[ATTENZIONE] WebView2 Runtime non rilevato su questa macchina.")
        print(
            "             L'exe verra compilato comunque, ma per eseguire la WebUI serve WebView2."
        )
        print(f"             Download ufficiale: {download_url}")
    print(
        "             Suggerimento: comunica questo prerequisito anche agli utenti finali Windows."
    )
    print()


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
    ensure_supported_node_version()
    if skip_npm_install:
        return
    run(["npm", "install", "--no-audit", "--no-fund"], cwd=WEBUI_DIR)


def run_pyright() -> None:
    run([sys.executable, "-m", "pyright"])


def run_python_checks(with_coverage: bool = False) -> None:
    existing_targets = [
        str(ROOT / target)
        for target in PYTHON_CHECK_TARGETS
        if (ROOT / target).exists()
    ]
    run([sys.executable, "-m", "ruff", "check", *existing_targets])
    run([sys.executable, "-m", "ruff", "format", "--check", *existing_targets])
    if with_coverage:
        run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/",
                "-q",
                "--cov=el_sbobinator",
                "--cov-report=xml:coverage-python.xml",
                "--cov-report=term-missing",
                "--cov-fail-under=69",
            ]
        )
    else:
        run([sys.executable, "-m", "pytest", "tests/", "-q"])
    run_pyright()


def run_webui_checks(skip_npm_install: bool, with_coverage: bool = False) -> None:
    install_node_dependencies(skip_npm_install=skip_npm_install)
    run(["npm", "run", "lint"], cwd=WEBUI_DIR)
    run(["npm", "run", "typecheck"], cwd=WEBUI_DIR)
    if with_coverage:
        run(["npm", "run", "test:coverage"], cwd=WEBUI_DIR)
    else:
        run(["npm", "test"], cwd=WEBUI_DIR)


def build_webui(skip_npm_install: bool) -> None:
    install_node_dependencies(skip_npm_install=skip_npm_install)
    run(["npm", "run", "build"], cwd=WEBUI_DIR)


def pyinstaller_command(target: str, ui: str) -> list[str]:
    spec_dir = PACKAGING_DIR / ("windows" if target == "windows" else "macos")
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--specpath",
        str(spec_dir),
    ]
    if target == "windows":
        command.extend(["--clean", "--onedir", "--windowed"])
        command.extend(["--icon", str(ROOT / "assets" / "icon.ico")])
    else:
        command.extend(["--windowed"])
        command.extend(["--icon", str(ROOT / "assets" / "icon.icns")])

    command.extend(
        [
            "--add-data",
            "webui/dist;webui/dist" if os.name == "nt" else "webui/dist:webui/dist",
            "--collect-all",
            "imageio_ffmpeg",
            "--collect-all",
            "keyring",
            "--collect-all",
            "html2docx",
            "--hidden-import",
            "webview",
            "--hidden-import",
            "clr",
            "--name",
            APP_NAME,
            str(WEBVIEW_ENTRYPOINT),
        ]
    )
    return command


def artifact_path(target: str) -> Path:
    if target == "windows":
        return ROOT / "dist" / APP_NAME  # onedir folder
    return ROOT / "dist" / f"{APP_NAME}.app"


def run_postbuild_smoke(target: str) -> None:
    expected = artifact_path(target)
    if not expected.exists():
        raise FileNotFoundError(f"Artifact mancante dopo la build: {expected}")
    if target == "windows":
        inner_exe = expected / f"{APP_NAME}.exe"
        if not inner_exe.exists() or inner_exe.stat().st_size <= 0:
            raise RuntimeError(f"Executable interno mancante o vuoto: {inner_exe}")
    else:
        if not any(expected.iterdir()):
            raise RuntimeError(f"Artifact vuoto o corrotto: {expected}")
    run([sys.executable, "scripts/smoke_test.py"], cwd=ROOT)


def _find_iscc() -> str:
    in_path = shutil.which("ISCC") or shutil.which("ISCC.exe")
    if in_path:
        return in_path
    for candidate in [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]:
        if Path(candidate).exists():
            return candidate
    return "ISCC.exe"


def run_inno_setup(version: str) -> None:
    iss_script = PACKAGING_DIR / "windows" / "installer.iss"
    run([_find_iscc(), f"/DAppVersion={version}", str(iss_script)], cwd=ROOT)
    installer = ROOT / "dist" / f"El-Sbobinator-Setup-v{version}.exe"
    if not installer.exists() or installer.stat().st_size <= 0:
        raise FileNotFoundError(f"Installer mancante o vuoto: {installer}")


def run_create_dmg(version: str) -> None:
    app_path = ROOT / "dist" / f"{APP_NAME}.app"
    dmg_path = ROOT / "dist" / f"El-Sbobinator-v{version}.dmg"
    run(
        [
            "create-dmg",
            "--volname",
            APP_NAME,
            "--window-pos",
            "200",
            "120",
            "--window-size",
            "600",
            "400",
            "--icon-size",
            "100",
            "--app-drop-link",
            "450",
            "185",
            str(dmg_path),
            str(app_path),
        ],
        cwd=ROOT,
    )
    if not dmg_path.exists() or dmg_path.stat().st_size <= 0:
        raise FileNotFoundError(f"DMG mancante o vuoto: {dmg_path}")


def command_deps(args: argparse.Namespace) -> None:
    install_python_dependencies(include_dev=bool(args.dev))
    install_packaging_dependencies(args.ui)
    if args.ui == "webui":
        install_node_dependencies(skip_npm_install=bool(args.skip_npm_install))


def command_check(args: argparse.Namespace) -> None:
    with_coverage = bool(args.with_coverage)
    if not args.skip_python:
        run_python_checks(with_coverage=with_coverage)
    if not args.skip_webui:
        run_webui_checks(
            skip_npm_install=bool(args.skip_npm_install), with_coverage=with_coverage
        )


def command_build(args: argparse.Namespace) -> None:
    print_windows_webview2_notice(args.target, args.ui)

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

    if args.target == "windows":
        run_inno_setup(args.version)
    elif args.target == "macos":
        run_create_dmg(args.version)


def command_validate(args: argparse.Namespace) -> None:
    from el_sbobinator.services.validation_service import validate_environment

    result = validate_environment(
        api_key=args.api_key, validate_api_key=bool(args.check_api_key)
    )
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
    check_parser.add_argument("--with-coverage", action="store_true")
    check_parser.set_defaults(func=command_check)

    build_parser = subparsers.add_parser("build", help="Build the distributable app")
    build_parser.add_argument("--target", choices=["windows", "macos"], required=True)
    build_parser.add_argument("--ui", choices=["webui"], default="webui")
    build_parser.add_argument("--install-deps", action="store_true")
    build_parser.add_argument("--dev-deps", action="store_true")
    build_parser.add_argument("--skip-npm-install", action="store_true")
    build_parser.add_argument("--skip-checks", action="store_true")
    build_parser.add_argument("--skip-postbuild-smoke", action="store_true")
    build_parser.add_argument("--version", default="0.0.0")
    build_parser.set_defaults(func=command_build)

    validate_parser = subparsers.add_parser(
        "validate", help="Validate local environment and optional API access"
    )
    validate_parser.add_argument("--api-key", default="")
    validate_parser.add_argument("--check-api-key", action="store_true")
    validate_parser.set_defaults(func=command_validate)

    smoke_parser = subparsers.add_parser(
        "smoke", help="Run smoke tests and optional post-build artifact checks"
    )
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
