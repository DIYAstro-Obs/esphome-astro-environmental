"""The calculated values: dew point, cloud cover and wind speed.

The formulas live in the lambdas of esphome-astro-environmental/features/*.yaml (C++). Here they are written
once more in Python, checked against known values, and the YAML is checked for the same constants and the same
expressions, so the documented formula and the firmware cannot drift apart silently. (The C++ itself is only
compiled by `esphome compile`, it is not executed here.)
"""
import math
import pathlib

import pytest

FEATURES = pathlib.Path(__file__).resolve().parents[1] / "esphome-astro-environmental" / "features"


def dew_point(t: float, rh: float) -> float:
    gamma = math.log(rh / 100.0) + 17.62 * t / (243.12 + t)
    return 243.12 * gamma / (17.62 - gamma)


def cloud_cover(delta: float, clear: float, overcast: float) -> float:
    percent = (delta - clear) / (overcast - clear) * 100.0
    return min(100.0, max(0.0, percent))


def wind_speed_kmh(pulses_per_minute: float, pulses_per_revolution: float, kmh_per_rps: float) -> float:
    return pulses_per_minute / pulses_per_revolution / 60.0 * kmh_per_rps


@pytest.mark.parametrize(
    "t, rh, expected",
    [
        (20.0, 50.0, 9.26),   # the usual textbook example (about 9.3 degC)
        (25.0, 100.0, 25.0),  # saturated air: the dew point is the temperature
        (0.0, 100.0, 0.0),
        (-10.0, 80.0, -12.8),
        (30.0, 40.0, 14.9),
    ],
)
def test_dew_point_follows_the_magnus_formula(t, rh, expected):
    assert dew_point(t, rh) == pytest.approx(expected, abs=0.1)


def buck_saturation_pressure(t: float) -> float:
    """Saturation vapour pressure over water in kPa (Buck 1996): an independent formula."""
    return 0.61121 * math.exp((18.678 - t / 234.5) * (t / (257.14 + t)))


def buck_dew_point(t: float, rh: float) -> float:
    """The temperature at which the saturation pressure equals the actual vapour pressure (bisection)."""
    pressure = rh / 100.0 * buck_saturation_pressure(t)
    low, high = -80.0, t
    for _ in range(80):
        middle = (low + high) / 2.0
        if buck_saturation_pressure(middle) < pressure:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def test_dew_point_agrees_with_an_independent_formula():
    # Magnus (Sonntag constants) against Buck: the largest difference over -20..40 degC and 10..100 % is 0.06 K
    for t in range(-20, 41):
        for rh in range(10, 101, 5):
            assert dew_point(float(t), float(rh)) == pytest.approx(buck_dew_point(float(t), float(rh)), abs=0.1)


def test_dew_point_is_never_above_the_temperature():
    for t in range(-20, 41, 5):
        for rh in range(10, 101, 10):
            assert dew_point(float(t), float(rh)) <= t + 1e-9


@pytest.mark.parametrize(
    "delta, expected",
    [(-30.0, 0.0), (-25.0, 0.0), (-16.5, 50.0), (-8.0, 100.0), (-2.0, 100.0)],
)
def test_cloud_cover_is_linear_between_the_limits_and_clamped(delta, expected):
    assert cloud_cover(delta, clear=-25.0, overcast=-8.0) == pytest.approx(expected)


def test_shifting_both_limits_shifts_the_curve():
    # limits set for another season: the same delta gives another cover (3.5 of 17 K above Clear = 20.6 %)
    assert cloud_cover(-16.5, clear=-25.0, overcast=-8.0) == pytest.approx(50.0)
    assert cloud_cover(-16.5, clear=-20.0, overcast=-3.0) == pytest.approx(20.6, abs=0.1)


@pytest.mark.parametrize(
    "rate, per_rev, factor, expected",
    [
        (0.0, 1.0, 2.4, 0.0),
        (60.0, 1.0, 2.4, 2.4),    # one revolution per second
        (600.0, 1.0, 2.4, 24.0),  # ten revolutions per second
        (120.0, 2.0, 2.4, 2.4),   # two pulses per revolution
    ],
)
def test_wind_speed_from_the_pulse_rate(rate, per_rev, factor, expected):
    assert wind_speed_kmh(rate, per_rev, factor) == pytest.approx(expected)


# --- the YAML has to say the same ---

def read(name: str) -> str:
    return (FEATURES / name).read_text(encoding="utf-8")


def test_the_dew_point_lambda_uses_the_documented_constants():
    text = read("bme280.yaml")
    assert "logf(rh / 100.0f) + 17.62f * t / (243.12f + t)" in text
    assert "243.12f * gamma / (17.62f - gamma)" in text
    assert "rh <= 0.0f" in text  # no logarithm of zero


def test_the_cloud_cover_lambda_uses_the_documented_expression():
    text = read("sky.yaml")
    assert "(delta - clear) / (overcast - clear) * 100.0f" in text
    assert "overcast <= clear" in text  # equal or reversed limits give no value
    assert "percent < 0.0f" in text and "percent > 100.0f" in text


def test_the_wind_lambda_uses_the_documented_expression():
    text = read("wind.yaml")
    assert "rate / per_revolution / 60.0f * kmh_per_rps" in text
    assert "initial_value: 2.4" in text and "initial_value: 1\n" in text
