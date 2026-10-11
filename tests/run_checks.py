#!/usr/bin/env python3
"""Local checks for the astro-environmental station (run on Linux / inside WSL, started by scripts/check.ps1).

Steps (the same as the CI workflow):
  1. firmware: dummy secrets, `esphome config` and `esphome compile` of astro-environmental.yaml
  2. examples: `esphome config` and `esphome compile` of every esphome-astro-environmental/config/examples/*.yaml
  3. tests:    the configuration and formula tests (pytest)

The repository is mirrored into ~/.cache/astro-env-checks (builds on /mnt/c are slow). Real secrets
(secrets.yaml, *.secrets) are never copied. Only the Python standard library is used here; the tools
are installed into a virtual environment at ~/.cache/astro-env-venv.

Usage:
  run_checks.py                      firmware, examples and tests
  run_checks.py --tests-only         only the tests
  run_checks.py --firmware-only      only the firmware and example compile
  run_checks.py -k wind              everything after the options goes to pytest

Exit code: 0 all passed, 1 a check failed, 2 the environment is not ready.
"""
import argparse
import hashlib
import pathlib
import shutil
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[1]
HOME = pathlib.Path.home()
VENV = HOME / ".cache" / "astro-env-venv"
WORK = HOME / ".cache" / "astro-env-checks"
LOGS = WORK / "logs"
ENTRY = "astro-environmental.yaml"
CONFIG = "esphome-astro-environmental/config/astro-environmental-config.yaml"

# build caches that survive between runs
KEEP = {".esphome", "logs"}
# never mirrored: caches, local secrets, planning notes
IGNORE = shutil.ignore_patterns(
    ".git", ".esphome", "__pycache__", ".pytest_cache", "secrets.yaml", "*.secrets", "memory-bank", "plans",
)

APT_HINT = "sudo apt install build-essential python3-venv python3-pip"


def say(text=""):
    print(text, flush=True)


def ascii_only(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def mirror(dst: pathlib.Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for child in dst.iterdir():
        if child.name in KEEP:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.copytree(REPO, dst, ignore=IGNORE, dirs_exist_ok=True)


def ensure_venv() -> pathlib.Path:
    py = VENV / "bin" / "python"
    if not py.exists():
        say("[setup] creating virtual environment " + str(VENV))
        result = subprocess.run([sys.executable, "-m", "venv", str(VENV)], capture_output=True, text=True)
        if result.returncode != 0:
            say(ascii_only(result.stderr.strip()))
            say("[!] python venv is not available. Install it with: " + APT_HINT)
            sys.exit(2)
    req = REPO / "tests" / "requirements.txt"
    digest = hashlib.sha256(req.read_bytes()).hexdigest()
    stamp = VENV / ".requirements.sha256"
    if not stamp.exists() or stamp.read_text().strip() != digest:
        say("[setup] installing test requirements (esphome, pytest) ...")
        result = subprocess.run(
            [str(py), "-m", "pip", "install", "-q", "--upgrade", "-r", str(req)], capture_output=True, text=True
        )
        if result.returncode != 0:
            say(ascii_only(result.stdout[-2000:] + result.stderr[-2000:]))
            say("[!] installing the requirements failed")
            sys.exit(2)
        stamp.write_text(digest)
    return py


def run_logged(name: str, cmd, cwd: pathlib.Path) -> bool:
    """Run quietly into a log file; show the tail only when it fails."""
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / (name.replace(" ", "_") + ".log")
    with open(log, "wb") as fh:
        code = subprocess.run(cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT).returncode
    if code != 0:
        text = log.read_text(errors="replace").splitlines()
        say(ascii_only("\n".join(text[-40:])))
        say("[!] " + name + " failed, full log: " + str(log))
    return code == 0


def check_firmware(py: pathlib.Path) -> bool:
    work = WORK / "firmware"
    mirror(work)
    shutil.copy(work / "tests" / "ci" / "secrets.ci.yaml", work / "secrets.yaml")
    esphome = [str(py), "-m", "esphome"]
    if not run_logged("esphome config", esphome + ["config", ENTRY], work):
        return False
    return run_logged("esphome compile", esphome + ["compile", ENTRY], work)


def check_examples(py: pathlib.Path) -> bool:
    """Every example configuration has to validate and compile (it replaces astro-environmental-config.yaml)."""
    examples = sorted((REPO / "esphome-astro-environmental/config/examples").glob("*.yaml"))
    work = WORK / "firmware"
    mirror(work)  # keeps the build cache: only the configuration changes between the examples
    shutil.copy(work / "tests" / "ci" / "secrets.ci.yaml", work / "secrets.yaml")
    esphome = [str(py), "-m", "esphome"]
    ok = True
    for example in examples:
        say("   " + example.name)
        shutil.copy(example, work / CONFIG)
        ok = run_logged("esphome config " + example.stem, esphome + ["config", ENTRY], work) and ok
        ok = run_logged("esphome compile " + example.stem, esphome + ["compile", ENTRY], work) and ok
    return ok


def check_tests(py: pathlib.Path, pytest_args) -> "tuple[bool, str]":
    work = WORK / "tests-repo"
    mirror(work)
    cmd = [str(py), "-m", "pytest", "-rxXf", "--tb=short", "--show-capture=no", "-p", "no:cacheprovider"]
    cmd += list(pytest_args)
    proc = subprocess.Popen(cmd, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    last = ""
    for line in proc.stdout:
        line = ascii_only(line.rstrip("\n"))
        say(line)
        if line.strip():
            last = line.strip("= ").strip()
    return proc.wait() == 0, last


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tests-only", action="store_true", help="only the tests")
    parser.add_argument("--firmware-only", action="store_true", help="only the firmware and example compile")
    args, pytest_args = parser.parse_known_args()
    if args.tests_only and args.firmware_only:
        parser.error("--tests-only and --firmware-only exclude each other")
    if not sys.platform.startswith("linux"):
        say("[!] run this inside WSL / on Linux (scripts/check.ps1 does that for you)")
        return 2

    py = ensure_venv()
    results = []  # (name, ok, seconds, detail)

    if not args.tests_only:
        say("")
        say("== firmware (config + compile) ==")
        start = time.monotonic()
        results.append(("firmware", check_firmware(py), time.monotonic() - start, ""))
        say("")
        say("== example configurations (config + compile) ==")
        start = time.monotonic()
        results.append(("example configs", check_examples(py), time.monotonic() - start, ""))

    if not args.firmware_only:
        say("")
        say("== tests ==")
        start = time.monotonic()
        ok, last = check_tests(py, pytest_args)
        results.append(("tests", ok, time.monotonic() - start, last))

    say("")
    say("== summary ==")
    for name, ok, seconds, detail in results:
        say("%-20s %-6s %4.0f s  %s" % (name, "OK" if ok else "FAILED", seconds, detail))
    return 0 if all(ok for _, ok, _, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
