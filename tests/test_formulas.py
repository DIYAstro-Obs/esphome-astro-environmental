"""The calculated values: dew point, cloud cover, wind speed and the sky quality.

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


# TSL2591 at gain 9500x and 600 ms integration, device factor 53 and glass attenuation 7.7 (the ESPHome defaults)
COUNTS_PER_LUX = 600.0 * 9500.0 / (53.0 * 7.7)
DARK_LIMIT = 120.0  # the datasheet: 0 to 20 counts at 100 ms, so at most about 120 counts at 600 ms


def illuminance_lux(counts: float, dark: float) -> float:
    net = counts - dark
    return float("nan") if net <= 0.0 else net / COUNTS_PER_LUX


def sky_quality(counts: float, dark: float, offset: float = 0.0) -> float:
    lux = illuminance_lux(counts, dark)
    if math.isnan(lux):
        return float("nan")
    return -2.5 * math.log10(lux / (math.pi * 1.08e5)) + offset


def sky_luminance_mcd(magnitude: float) -> float:
    return 1000.0 * 1.08e5 * 10.0 ** (-0.4 * magnitude)


def dark_calibration(minutes: list) -> "tuple[str, float | None]":
    """The rule of the "Calibrate Dark Counts" button: the minute that was already running is discarded, the mean of
    the next ten minutes is stored; a saturated minute (None) or a mean above the datasheet limit is a failure,
    a negative mean is stored as 0."""
    values = minutes[1:11]
    if len(values) < 10:
        return "running", None
    if any(v is None for v in values):
        return "failed: saturated", None
    mean = sum(values) / 10.0
    if mean > DARK_LIMIT:
        return "failed: light leak", None
    return "done", max(mean, 0.0)


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


def test_counts_per_lux_of_the_chip_at_its_highest_sensitivity():
    # 600 ms * 9500 / (53 * 7.7): one count is about 72 microlux
    assert COUNTS_PER_LUX == pytest.approx(13967.0, abs=1.0)
    assert 1.0 / COUNTS_PER_LUX * 1e6 == pytest.approx(71.6, abs=0.1)


@pytest.mark.parametrize(
    "counts, dark, expected",
    [
        (7.5, 0.0, 22.0),    # a dark rural sky: about 0.0005 lx
        (75.0, 0.0, 19.5),   # ten times the counts are 2.5 magnitudes brighter
        (27.5, 20.0, 22.0),  # the dark counts are subtracted before anything else
        (750.0, 0.0, 17.0),
    ],
)
def test_sky_quality_from_the_counts(counts, dark, expected):
    assert sky_quality(counts, dark) == pytest.approx(expected, abs=0.05)


def test_the_offset_is_added_to_the_magnitude():
    assert sky_quality(7.5, 0.0, offset=0.3) == pytest.approx(sky_quality(7.5, 0.0) + 0.3)
    assert sky_quality(7.5, 0.0, offset=-0.5) == pytest.approx(sky_quality(7.5, 0.0) - 0.5)


@pytest.mark.parametrize("counts, dark", [(5.0, 5.0), (3.0, 5.0), (0.0, 0.0)])
def test_no_light_above_the_dark_counts_is_no_value(counts, dark):
    assert math.isnan(sky_quality(counts, dark))
    assert math.isnan(illuminance_lux(counts, dark))


def test_illuminance_of_a_dark_sky():
    assert illuminance_lux(7.5, 0.0) == pytest.approx(0.000537, abs=0.00001)


@pytest.mark.parametrize("magnitude, expected", [(22.0, 0.171), (21.0, 0.430), (19.0, 2.71), (18.0, 6.80)])
def test_sky_luminance_in_mcd_per_m2(magnitude, expected):
    assert sky_luminance_mcd(magnitude) == pytest.approx(expected, rel=0.01)


def test_luminance_and_illuminance_agree_for_a_uniform_hemisphere():
    # L = E / pi: the two values come from the same counts
    for counts in (7.5, 40.0, 300.0):
        lux = illuminance_lux(counts, 0.0)
        luminance_cd = sky_luminance_mcd(sky_quality(counts, 0.0)) / 1000.0
        assert luminance_cd == pytest.approx(lux / math.pi, rel=1e-6)


def test_dark_calibration_discards_the_running_minute_and_takes_the_mean_of_ten():
    minutes = [500.0] + [10.0, 12.0, 8.0, 10.0, 11.0, 9.0, 10.0, 10.0, 12.0, 8.0]  # the first one was not covered
    assert dark_calibration(minutes) == ("done", pytest.approx(10.0))
    assert dark_calibration(minutes[:6])[0] == "running"


def test_dark_calibration_fails_with_light():
    saturated = [10.0] + [10.0] * 4 + [None] + [10.0] * 5
    assert dark_calibration(saturated)[0] == "failed: saturated"
    assert dark_calibration([0.0] + [130.0] * 10)[0] == "failed: light leak"
    assert dark_calibration([0.0] + [120.0] * 10) == ("done", pytest.approx(120.0))


def test_a_negative_dark_mean_is_stored_as_zero():
    assert dark_calibration([0.0] + [-0.4] * 10) == ("done", 0.0)


# --- the YAML has to say the same ---

def read(name: str) -> str:
    return (FEATURES / name).read_text(encoding="utf-8")


def test_the_dew_point_lambda_uses_the_documented_constants():
    text = read("dew_point.yaml")
    assert "logf(rh / 100.0f) + 17.62f * t / (243.12f + t)" in text
    assert "243.12f * gamma / (17.62f - gamma)" in text
    assert "rh <= 0.0f" in text  # no logarithm of zero


def test_the_cloud_cover_lambda_uses_the_documented_expression():
    text = read("cloud_cover.yaml")
    assert "(delta - clear) / (overcast - clear) * 100.0f" in text
    assert "overcast <= clear" in text  # equal or reversed limits give no value
    assert "percent < 0.0f" in text and "percent > 100.0f" in text


def test_the_wind_lambda_uses_the_documented_expression():
    text = read("wind.yaml")
    assert "rate / per_revolution / 60.0f * kmh_per_rps" in text
    assert "initial_value: 2.4" in text and "initial_value: 1\n" in text


def test_the_sky_quality_lambda_uses_the_documented_expression():
    text = read("sqm.yaml")
    assert "const float net = counts - dark;" in text
    assert "net <= 0.0f" in text  # no light above the dark counts: no value, no logarithm of zero
    assert "net / (600.0f * 9500.0f / (53.0f * 7.7f))" in text
    assert "-2.5f * log10f(lux / (3.14159265f * 1.08e5f)) + offset" in text
    # a saturated reading is not a value, and the difference of the channels is not clamped
    assert "full >= 65535.0f" in text
    assert "publish_state(full - x)" in text


def test_the_sky_luminance_lambda_uses_the_documented_expression():
    text = read("sky_luminance.yaml")
    assert "1000.0f * 1.08e5f * powf(10.0f, -0.4f * x)" in text
    assert "std::isnan(x)" in text


def test_the_dark_calibration_uses_the_documented_rule():
    text = read("sqm.yaml")
    assert "id(sqm_cal_n) = -1;" in text                 # the minute that is running is discarded
    assert "id(sqm_cal_n) < 10" in text                  # ten minutes
    assert "id(sqm_cal_sum) / 10.0f" in text             # the mean
    assert "mean > 120.0f" in text                       # the limit of the datasheet at 600 ms
    assert "if (mean < 0.0f) mean = 0.0f;" in text
    assert "std::isnan(x)" in text                       # a saturated minute fails
    assert "max_value: 1000" in text                     # the setting accepts what the rule can store
