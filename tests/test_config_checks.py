"""Checks of astro-environmental-config.yaml: a wrong configuration has to fail when ESPHome validates it, with a
message that names the problem (esphome-astro-environmental/config/checks.yaml), and a right one has to produce
exactly the entities that are built. These tests only validate the configuration (`esphome config`, a few seconds
each), nothing is compiled.
"""
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES = sorted((REPO / "esphome-astro-environmental/config/examples").glob("*.yaml"))
CONFIG = "esphome-astro-environmental/config/astro-environmental-config.yaml"


def render(value) -> str:
    if isinstance(value, str) and value.startswith("0x"):
        return f'"{value}"'  # an address stays a string (an unquoted 0x76 is a YAML integer)
    return str(value)


def run_config(tmp_path: pathlib.Path, overrides: dict, base: "pathlib.Path | None" = None) -> "tuple[int, str]":
    """`esphome config` of the real entry file with some keys of astro-environmental-config.yaml replaced
    (`base`: another file instead of the shipped configuration, e.g. an example)."""
    work = tmp_path / "project"
    shutil.copytree(
        REPO / "esphome-astro-environmental", work / "esphome-astro-environmental",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copy(REPO / "astro-environmental.yaml", work)
    shutil.copy(REPO / "tests/ci/secrets.ci.yaml", work / "secrets.yaml")

    config = work / CONFIG
    if base is not None:
        shutil.copy(base, config)
    text = config.read_text(encoding="utf-8")
    for key, value in overrides.items():
        text, count = re.subn(rf"^{key}:.*$", f"{key}: {render(value)}", text, flags=re.M)
        assert count == 1, f"key {key} is not in astro-environmental-config.yaml"
    config.write_text(text, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "esphome", "config", "astro-environmental.yaml"],
        cwd=work, capture_output=True, text=True,
    )
    return result.returncode, result.stdout + result.stderr


NOT_USABLE = "CONFIG_ERROR_a_pin_is_not_a_usable_gpio_number_of_this_board_or_none_for_a_sensor_that_is_built"

INVALID = [
    ({"log_level": "TRACE"}, "CONFIG_ERROR_log_level_must_be_DEBUG_or_INFO_or_WARN"),
    ({"bme280": "maybe"}, "CONFIG_ERROR_bme280_must_be_true_or_false"),
    ({"rain": "maybe"}, "CONFIG_ERROR_rain_must_be_true_or_false"),
    ({"sky": "maybe"}, "CONFIG_ERROR_sky_must_be_true_or_false"),
    ({"wind": "maybe"}, "CONFIG_ERROR_wind_must_be_true_or_false"),
    ({"rain_inverted": "sometimes"}, "CONFIG_ERROR_rain_inverted_must_be_true_or_false"),
    (
        {"bme280": "false", "rain": "false", "sky": "false", "wind": "false"},
        "CONFIG_ERROR_at_least_one_sensor_must_be_built",
    ),
    ({"pin_rain": 6}, NOT_USABLE),  # flash
    ({"pin_wind": 40}, NOT_USABLE),
    ({"pin_wind": "none"}, NOT_USABLE),  # built, but no pin
    ({"pin_rain": 21}, "CONFIG_ERROR_a_pin_is_used_for_two_functions"),  # SDA
    ({"pin_wind": 25}, "CONFIG_ERROR_a_pin_is_used_for_two_functions"),  # rain
    ({"pin_wind": 34}, "CONFIG_ERROR_pin_wind_needs_a_pull_up_use_a_gpio_other_than_34_to_39"),
    ({"pin_sda": 34}, "CONFIG_ERROR_pin_sda_and_pin_scl_must_not_be_an_input_only_gpio_34_to_39"),
    ({"bme280_address": "0x78"}, "CONFIG_ERROR_bme280_address_must_be_0x76_or_0x77"),
    ({"mlx90614_address": "5A"}, "CONFIG_ERROR_mlx90614_address_must_look_like_0x5A"),
]


@pytest.mark.parametrize("overrides, error", INVALID, ids=lambda v: v if isinstance(v, str) else None)
def test_a_wrong_configuration_fails_with_a_message_that_names_the_problem(tmp_path, overrides, error):
    code, output = run_config(tmp_path, overrides)
    assert code != 0, "the configuration was accepted"
    assert error in output, output[:1500]


def test_an_unknown_board_is_refused(tmp_path):
    code, output = run_config(tmp_path, {"hardware": "esp32_c3"})
    assert code != 0
    assert "hw_esp32_c3" in output or "CONFIG_ERROR_hardware_is_not_a_known_board" in output, output[:1500]


# what has to exist (and what must not) for each configuration: the entity names of the features
ALL = {"Temperature", "Humidity", "Pressure", "Dew Point", "Rain", "Sky Temperature", "Sky Temperature Delta",
       "Cloud Cover", "Cloud Clear Delta", "Cloud Overcast Delta", "Wind Speed", "Wind Gust",
       "Wind Pulses per Revolution", "Wind Speed per Revolution per Second"}
DIAGNOSTIC = {"Free Heap", "Min Free Heap", "Uptime", "Reset Reason", "WiFi RSSI", "IP Address", "WiFi SSID",
              "WiFi BSSID"}
BME = {"Temperature", "Humidity", "Pressure", "Dew Point"}
SKY = {"Sky Temperature", "Sky Sensor Ambient", "Sky Temperature Delta", "Cloud Cover", "Cloud Clear Delta",
       "Cloud Overcast Delta"}
WIND = {"Wind Speed", "Wind Gust", "Wind Pulses per Revolution", "Wind Speed per Revolution per Second"}

VALID = [
    pytest.param({}, None, BME | SKY | WIND | {"Rain"}, id="default"),
    pytest.param({"bme280_address": "0x77"}, None, BME | SKY | WIND | {"Rain"}, id="bme280-at-0x77"),
    pytest.param({"rain_inverted": "false"}, None, BME | SKY | WIND | {"Rain"}, id="rain-not-inverted"),
    pytest.param({"wind": "false", "pin_wind": "none"}, None, BME | SKY | {"Rain"}, id="without-wind"),
    pytest.param({"sky": "false"}, None, BME | WIND | {"Rain"}, id="without-sky"),
    pytest.param({"bme280": "false"}, None, SKY | WIND | {"Rain"}, id="without-bme280"),
]


@pytest.mark.parametrize("overrides, base, expected", VALID)
def test_a_right_configuration_builds_exactly_the_entities_that_are_wired(tmp_path, overrides, base, expected):
    code, output = run_config(tmp_path, overrides, base)
    assert code == 0, output[-2500:]
    for name in DIAGNOSTIC:
        assert f"name: {name}" in output, f"{name} is missing"
    for name in expected:
        assert f"name: {name}" in output, f"{name} is missing"
    for name in ALL - expected:
        assert f"name: {name}" not in output, f"{name} exists although its sensor is not built"


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.stem)
def test_every_example_validates(tmp_path, example):
    code, output = run_config(tmp_path, {}, base=example)
    assert code == 0, output[-2500:]
