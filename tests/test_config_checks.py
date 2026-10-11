"""Checks of astro-environmental-config.yaml: a wrong configuration has to fail when ESPHome validates it, with a
message that names the problem (esphome-astro-environmental/config/checks.yaml), and a right one has to produce
exactly the entities that are built. A sensor that is switched off is not reported to Home Assistant, and everything
that is calculated from it is not built either. These tests only validate the configuration (`esphome config`, a
few seconds each), nothing is compiled.
"""
import pathlib
import re
import shutil
import subprocess
import sys

import pytest
import yaml

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


class _Loader(yaml.SafeLoader):
    """Reads the dump of `esphome config`, which contains tags such as !lambda."""


def _any_tag(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_mapping(node, deep=True)


_Loader.add_multi_constructor("!", _any_tag)


def load_config(output: str) -> dict:
    lines = [line for line in output.splitlines() if not line.startswith(("INFO ", "WARNING ", "ERROR "))]
    return yaml.load("\n".join(lines), Loader=_Loader)


def exposed_entities(config: dict) -> set:
    """The names of the entities that Home Assistant gets (internal entities are not reported)."""
    names = set()

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("name"), str) and node.get("internal") is not True:
                names.add(node["name"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for domain in ("sensor", "binary_sensor", "number", "text_sensor", "switch"):
        walk(config.get(domain))
    return names


NOT_USABLE = "CONFIG_ERROR_a_pin_is_not_a_usable_gpio_number_of_this_board_or_none_for_a_sensor_that_is_built"
SWITCHES = ["sensor_temperature", "sensor_humidity", "sensor_pressure", "sensor_dew_point", "sensor_sky_temperature",
            "sensor_sky_ambient", "sensor_sky_delta", "sensor_cloud_cover", "sensor_wind_speed", "sensor_wind_gust"]

INVALID = [
    ({"log_level": "TRACE"}, "CONFIG_ERROR_log_level_must_be_DEBUG_or_INFO_or_WARN"),
    ({"bme280": "maybe"}, "CONFIG_ERROR_bme280_must_be_true_or_false"),
    ({"rain": "maybe"}, "CONFIG_ERROR_rain_must_be_true_or_false"),
    ({"sky": "maybe"}, "CONFIG_ERROR_sky_must_be_true_or_false"),
    ({"wind": "maybe"}, "CONFIG_ERROR_wind_must_be_true_or_false"),
    ({"rain_inverted": "sometimes"}, "CONFIG_ERROR_rain_inverted_must_be_true_or_false"),
    ({"sensor_pressure": "sometimes"}, "CONFIG_ERROR_a_sensor_switch_must_be_true_or_false"),
    ({"sensor_wind_gust": "sometimes"}, "CONFIG_ERROR_a_sensor_switch_must_be_true_or_false"),
    (
        {"bme280": "false", "rain": "false", "sky": "false", "wind": "false"},
        "CONFIG_ERROR_at_least_one_sensor_must_be_built",
    ),
    (
        {"rain": "false", **{key: "false" for key in SWITCHES}},
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


# the entity names of the features
BME = {"Temperature", "Humidity", "Pressure", "Dew Point"}
SKY = {"Sky Temperature", "Sky Sensor Ambient", "Sky Temperature Delta", "Cloud Cover"}
CLOUD_SETTINGS = {"Cloud Clear Delta", "Cloud Overcast Delta"}
WIND = {"Wind Speed", "Wind Gust"}
WIND_SETTINGS = {"Wind Pulses per Revolution", "Wind Speed per Revolution per Second"}
RAIN = {"Rain"}
DIAGNOSTIC = {"Free Heap", "Min Free Heap", "Uptime", "Reset Reason", "WiFi RSSI", "IP Address", "WiFi SSID",
              "WiFi BSSID"}
ALL = BME | SKY | CLOUD_SETTINGS | WIND | WIND_SETTINGS | RAIN
EVERYTHING = ALL

VALID = [
    pytest.param({}, EVERYTHING, id="default"),
    pytest.param({"bme280_address": "0x77"}, EVERYTHING, id="bme280-at-0x77"),
    pytest.param({"rain_inverted": "false"}, EVERYTHING, id="rain-not-inverted"),
    # groups
    pytest.param({"wind": "false", "pin_wind": "none"}, EVERYTHING - WIND - WIND_SETTINGS, id="without-wind"),
    pytest.param({"sky": "false"}, EVERYTHING - SKY - CLOUD_SETTINGS, id="without-sky"),
    pytest.param({"bme280": "false"}, EVERYTHING - BME, id="without-bme280"),
    pytest.param({"rain": "false", "pin_rain": "none"}, EVERYTHING - RAIN, id="without-rain"),
    # single sensors
    pytest.param({"sensor_pressure": "false"}, EVERYTHING - {"Pressure"}, id="pressure-off"),
    pytest.param({"sensor_dew_point": "false"}, EVERYTHING - {"Dew Point"}, id="dew-point-off"),
    pytest.param({"sensor_wind_gust": "false"}, EVERYTHING - {"Wind Gust"}, id="wind-gust-off"),
    pytest.param({"sensor_wind_speed": "false"}, EVERYTHING - {"Wind Speed"}, id="wind-speed-off"),
    pytest.param({"sensor_cloud_cover": "false"}, EVERYTHING - {"Cloud Cover"} - CLOUD_SETTINGS,
                 id="cloud-cover-off-takes-its-settings"),
    pytest.param(
        {"sensor_wind_speed": "false", "sensor_wind_gust": "false", "pin_wind": "none"},
        EVERYTHING - WIND - WIND_SETTINGS, id="both-wind-sensors-off-no-pin-needed",
    ),
    # calculated values follow their inputs
    pytest.param({"sensor_temperature": "false"}, EVERYTHING - {"Temperature", "Dew Point"},
                 id="temperature-off-takes-the-dew-point"),
    pytest.param({"sensor_humidity": "false"}, EVERYTHING - {"Humidity", "Dew Point"},
                 id="humidity-off-takes-the-dew-point"),
    pytest.param({"sensor_sky_temperature": "false"},
                 EVERYTHING - {"Sky Temperature", "Sky Temperature Delta", "Cloud Cover"} - CLOUD_SETTINGS,
                 id="sky-temperature-off-takes-delta-and-cloud-cover"),
    pytest.param({"sensor_sky_ambient": "false"},
                 EVERYTHING - {"Sky Sensor Ambient", "Sky Temperature Delta", "Cloud Cover"} - CLOUD_SETTINGS,
                 id="ambient-off-takes-delta-and-cloud-cover"),
    pytest.param({"sensor_sky_delta": "false"},
                 EVERYTHING - {"Sky Temperature Delta", "Cloud Cover"} - CLOUD_SETTINGS,
                 id="delta-off-takes-cloud-cover"),
    pytest.param({"bme280": "false", "sensor_dew_point": "true"}, EVERYTHING - BME,
                 id="dew-point-needs-its-group"),
]


@pytest.mark.parametrize("overrides, expected", VALID)
def test_a_right_configuration_builds_exactly_the_entities_that_are_wired(tmp_path, overrides, expected):
    code, output = run_config(tmp_path, overrides)
    assert code == 0, output[-2500:]
    exposed = exposed_entities(load_config(output))
    assert DIAGNOSTIC <= exposed, f"missing health sensors: {DIAGNOSTIC - exposed}"
    assert exposed - DIAGNOSTIC == expected, (
        f"missing: {sorted(expected - exposed)}, too many: {sorted(exposed - DIAGNOSTIC - expected)}"
    )


def test_without_a_sensor_on_the_bus_there_is_no_i2c_bus(tmp_path):
    # the BME280 entities and the sky group are off: no I2C bus, and the I2C pins may be `none`
    overrides = {"sensor_temperature": "false", "sensor_humidity": "false", "sensor_pressure": "false",
                 "sky": "false", "pin_sda": "none", "pin_scl": "none"}
    code, output = run_config(tmp_path, overrides)
    assert code == 0, output[-2500:]
    config = load_config(output)
    assert "i2c" not in config
    assert exposed_entities(config) - DIAGNOSTIC == RAIN | WIND | WIND_SETTINGS


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.stem)
def test_every_example_validates(tmp_path, example):
    code, output = run_config(tmp_path, {}, base=example)
    assert code == 0, output[-2500:]
