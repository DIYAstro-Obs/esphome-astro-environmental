"""The ESPHome bundle (scripts/make_bundle.py): no secrets inside, every file of the project inside, and a
configuration that was changed after the import still validates. The end-to-end tests need ESPHome (the venv of
scripts/check.ps1 has it); the repack tests are plain Python.
"""
import gzip
import importlib.util
import io
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_bundle", REPO / "scripts" / "make_bundle.py")
make_bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_bundle)

CONFIG = "esphome-astro-environmental/config/astro-environmental-config.yaml"


def archive(members: "dict[str, bytes]") -> bytes:
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tar:
            for name, data in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    return raw.getvalue()


def read(bundle: bytes) -> "tuple[dict, dict[str, bytes]]":
    with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as tar:
        files = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
    return json.loads(files.pop("manifest.json")), files


def esphome_bundle(**overrides) -> bytes:
    manifest = {
        "manifest_version": 1, "esphome_version": "2026.9.1", "config_filename": "a.yaml",
        "config_dir": "/home/runner/work/x", "files": ["a.yaml", "secrets.yaml"], "has_secrets": True,
    }
    manifest.update(overrides)
    return archive({
        "manifest.json": json.dumps(manifest).encode(),
        "secrets.yaml": b"api_encryption_key: AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=\n",
        "a.yaml": b"packed by esphome\n",
    })


def test_repack_removes_the_secrets_and_says_so():
    manifest, files = read(make_bundle.repack(esphome_bundle(), {}))
    assert "secrets.yaml" not in files
    assert "secrets.yaml" not in manifest["files"]
    assert manifest["has_secrets"] is False
    assert "config_dir" not in manifest


def test_repack_adds_the_project_files_that_are_missing_and_keeps_the_packed_ones():
    project = {"a.yaml": b"the copy of the project", "proj/features/none.yaml": b"# nothing\n"}
    manifest, files = read(make_bundle.repack(esphome_bundle(), project))
    assert files["proj/features/none.yaml"] == b"# nothing\n"
    assert files["a.yaml"] == b"packed by esphome\n"
    assert manifest["files"] == sorted(files)
    assert manifest["config_filename"] == "a.yaml"
    assert manifest["esphome_version"] == "2026.9.1"


def test_repack_is_deterministic():
    project = {"proj/one.yaml": b"1\n", "proj/two.yaml": b"2\n"}
    assert make_bundle.repack(esphome_bundle(), project) == make_bundle.repack(esphome_bundle(), project)


def test_verify_refuses_a_bundle_with_secrets():
    with pytest.raises(SystemExit):
        make_bundle.verify(esphome_bundle())  # still carries secrets.yaml and has_secrets: true


def test_verify_accepts_a_repacked_bundle():
    make_bundle.verify(make_bundle.repack(esphome_bundle(), {}))


# --- end to end: the real bundle of this project ---

@pytest.fixture(scope="module")
def esphome_api():
    return pytest.importorskip("esphome.bundle")


@pytest.fixture(scope="module")
def real_bundle(tmp_path_factory, esphome_api):
    output = tmp_path_factory.mktemp("bundle") / "astro-environmental.esphomebundle.tar.gz"
    make_bundle.build(REPO, output)
    return output


def test_the_bundle_has_no_secrets_and_every_file_of_the_project(real_bundle):
    manifest, files = read(real_bundle.read_bytes())
    assert not [name for name in files if name.endswith("secrets.yaml")]
    assert manifest["has_secrets"] is False
    project = {
        p.relative_to(REPO).as_posix()
        for p in (REPO / "esphome-astro-environmental").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    assert project <= set(files), sorted(project - set(files))
    assert "astro-environmental.yaml" in files
    # the examples travel with it: the user copies one over the configuration
    assert "esphome-astro-environmental/config/examples/esp32-devkit_full.yaml" in files


def test_esphome_can_read_the_bundle(real_bundle, esphome_api):
    manifest = esphome_api.read_bundle_manifest(real_bundle)
    assert manifest.config_filename == "astro-environmental.yaml"
    assert manifest.has_secrets is False


@pytest.mark.parametrize(
    "overrides",
    [{}, {"wind": "false", "pin_wind": "none"}, {"bme280": "false"}, {"sky": "false", "rain": "false"}],
    ids=["unchanged", "without-wind", "without-bme280", "without-sky-and-rain"],
)
def test_a_configuration_changed_after_the_import_still_validates(real_bundle, esphome_api, tmp_path, overrides):
    """The user imports the bundle and then switches hardware off in the Device Builder: every file has to be there."""
    extracted = esphome_api.extract_bundle(real_bundle, tmp_path / "imported")
    project = extracted.parent
    shutil.copy(REPO / "tests/ci/secrets.ci.yaml", project / "secrets.yaml")

    config = project / CONFIG
    text = config.read_text(encoding="utf-8")
    for key, value in overrides.items():
        text, count = re.subn(rf"^{key}:.*$", f"{key}: {value}", text, flags=re.M)
        assert count == 1, key
    config.write_text(text, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "esphome", "config", extracted.name], cwd=project, capture_output=True, text=True
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-2000:]
