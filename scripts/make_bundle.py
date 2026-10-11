#!/usr/bin/env python3
"""Create the ESPHome bundle of the station (a .esphomebundle.tar.gz for the ESPHome Device Builder).

`esphome bundle` packs the configuration and the files it loaded. Two things are corrected afterwards:

  1. It packs the VALUES of the secrets the configuration uses. A bundle built from a real secrets.yaml would
     publish them, and one built with the dummy secrets of the CI would hand a known API key to every user whose
     Device Builder lacks the key (the import adds missing keys). The secrets are removed again.
  2. It only packs the files that were loaded for this configuration. Whoever changes the configuration in the
     Device Builder (hardware switched off, for example) needs the others too. All files of the project are added.

The bundle is built in a temporary copy of the project with the dummy secrets of tests/ci/secrets.ci.yaml, so a real
secrets.yaml in the repository is never read.

Usage:  python scripts/make_bundle.py [--output dist/astro-environmental.esphomebundle.tar.gz]
Needs ESPHome (pip install -r tests/requirements.txt).
"""
import argparse
import gzip
import io
import json
import pathlib
import posixpath
import shutil
import subprocess
import sys
import tarfile
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
ENTRY = "astro-environmental.yaml"
PROJECT_DIR = "esphome-astro-environmental"
CI_SECRETS = "tests/ci/secrets.ci.yaml"
EXTENSION = ".esphomebundle.tar.gz"
DEFAULT_OUTPUT = "dist/astro-environmental" + EXTENSION
MANIFEST = "manifest.json"
SECRETS = "secrets.yaml"


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    """The same metadata as esphome.bundle uses, so the archive is deterministic."""
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(data))


def repack(bundle: bytes, project_files: "dict[str, bytes]") -> bytes:
    """Remove the secrets, add the project files that are missing and correct the manifest."""
    contents: "dict[str, bytes]" = {}
    with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as tar:
        for member in tar.getmembers():
            if member.isfile():
                contents[member.name] = tar.extractfile(member).read()

    manifest = json.loads(contents.pop(MANIFEST))
    for name in [n for n in contents if posixpath.basename(n) == SECRETS]:
        del contents[name]
    for name, data in project_files.items():
        contents.setdefault(name, data)  # what esphome packed stays as it is

    manifest["files"] = sorted(contents)
    manifest["has_secrets"] = False
    manifest.pop("config_dir", None)  # a path of the machine that built the bundle

    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tar:
            _add_bytes(tar, MANIFEST, json.dumps(manifest, indent=2).encode("utf-8"))
            for name in sorted(contents):
                _add_bytes(tar, name, contents[name])
    return raw.getvalue()


def verify(bundle: bytes) -> None:
    """Refuse a bundle that carries secrets or lacks its configuration."""
    with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as tar:
        names = tar.getnames()
        manifest = json.load(tar.extractfile(MANIFEST))
    leaked = [n for n in names if posixpath.basename(n) == SECRETS]
    if leaked:
        raise SystemExit(f"the bundle contains secrets: {leaked}")
    if manifest.get("has_secrets") is not False:
        raise SystemExit("the manifest does not say has_secrets: false")
    if manifest.get("config_filename") not in names:
        raise SystemExit("the configuration file is not in the bundle")


def build(repo: pathlib.Path, output: pathlib.Path) -> None:
    if not output.name.endswith(EXTENSION):
        raise SystemExit(f"the output file name has to end with {EXTENSION}")

    with tempfile.TemporaryDirectory(prefix="astro-bundle-") as tmp:
        work = pathlib.Path(tmp) / "project"
        work.mkdir()
        shutil.copy(repo / ENTRY, work / ENTRY)
        shutil.copytree(repo / PROJECT_DIR, work / PROJECT_DIR, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(repo / CI_SECRETS, work / SECRETS)  # dummy values, removed again below

        raw = work.parent / ("raw" + EXTENSION)
        subprocess.run([sys.executable, "-m", "esphome", "bundle", ENTRY, "-o", str(raw)], cwd=work, check=True)

        project_files = {
            path.relative_to(work).as_posix(): path.read_bytes()
            for path in sorted((work / PROJECT_DIR).rglob("*"))
            if path.is_file()
        }
        project_files[ENTRY] = (work / ENTRY).read_bytes()
        data = repack(raw.read_bytes(), project_files)

    verify(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    print(f"Bundle created: {output} ({len(data) / 1024:.1f} KB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="output file (default: %(default)s)")
    args = parser.parse_args()
    build(REPO, pathlib.Path(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
