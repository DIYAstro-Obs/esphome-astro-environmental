# Astro-Environmental

ESPHome firmware for an environment station of an astronomical observatory on an ESP32: temperature, humidity, pressure and the dew point (BME280), a rain sensor, the sky temperature and an estimated cloud cover (MLX90614 infrared thermometer), the wind speed and gusts (anemometer with a reed contact) and, optionally, the sky quality (TSL2591 light sensor). The values appear as entities in Home Assistant.

## Features

- **BME280**: temperature, humidity, pressure (station pressure) and the **dew point**, calculated on the device.
- **Rain**: a rain sensor module with a digital output as a `moisture` binary sensor, held against flicker.
- **Sky / clouds**: MLX90614 infrared thermometer: sky temperature, the delta to the sensor housing and the **cloud cover in %**, mapped from the delta between two limits that you set in Home Assistant.
- **Wind**: speed (mean of 60 s) and gust (maximum of 10 min) from a reed contact; pulses per revolution and speed per revolution are settings in Home Assistant.
- **Sky quality (optional)**: a TSL2591 light sensor at its highest sensitivity gives the sky brightness in mag/arcsec² (like a Sky Quality Meter), the illuminance in lx and the luminance in mcd/m², one value per minute. A dark calibration button and an offset make it usable; see [Sky Quality](#sky-quality-sqm) for what it can and cannot do.
- Hardware that is not fitted is switched off as a whole (`bme280`, `rain`, `sky`, `wind`, `sqm`): no bus access, no entities in Home Assistant and nothing calculated from it. Single values can be switched off too, and what is calculated from a switched-off value is not built either.
- WiFi, encrypted API and OTA, web interface with login, health sensors of the ESP32 and the WiFi link.
- One flat configuration file whose wrong values stop the build with a message that names the problem.

## Project Structure

```
astro-environmental.yaml                      entry point: ESP32, API, web interface, OTA and the package list
esphome-astro-environmental/
  station.yaml                                what is built (derived switches), the sensor packages, boot log, checks
  config/
    astro-environmental-config.yaml           the configuration (one flat list of keys)
    checks.yaml, checks/                      checks of the configuration, messages are file names (CONFIG_ERROR_...)
    examples/                                 ready configurations (all sensors, BME280 only, rain and wind only,
                                              selected single sensors, sky quality sensor)
  core/boot.yaml                              device name, minimum ESPHome version
  hardware/                                   the board and its I2C bus
  network/wifi.yaml                           WiFi
  features/                                   system monitor, WiFi monitor, the sensors and the calculated values
scripts/                                      build, deploy and check scripts (PowerShell), make_bundle.py
tests/                                        configuration tests, formula tests, local check runner
secrets.yaml.example                          template of the secrets
```

## Configuration

The station is configured in **`esphome-astro-environmental/config/astro-environmental-config.yaml`**. It is one flat list of keys; every key has to be present. Edit it and flash the device again (ESPHome dashboard: Install). Ready configurations are in `esphome-astro-environmental/config/examples/`: copy one over the configuration file.

| Key | Default | Meaning |
|---|---|---|
| `name` | `astro-environmental` | device name (host name `<name>.local`) |
| `log_level` | `DEBUG` | `DEBUG`, `INFO` or `WARN` |
| `hardware` | `esp32_devkit` | board, see `esphome-astro-environmental/hardware/` |
| `bme280` | `true` | hardware: the BME280 chip (temperature, humidity, pressure, dew point) |
| `rain` | `true` | hardware: the rain sensor module (Rain) |
| `sky` | `true` | hardware: the MLX90614 (sky temperature, delta, cloud cover) |
| `wind` | `true` | hardware: the anemometer (wind speed, gust) |
| `sqm` | `false` | hardware: the TSL2591 light sensor (sky quality, illuminance, luminance); optional, so it is off by default |
| `sensor_temperature`, `sensor_humidity`, `sensor_pressure` | `true` | single values of the BME280 |
| `sensor_dew_point` | `true` | calculated from temperature and humidity |
| `sensor_sky_temperature`, `sensor_sky_ambient` | `true` | single values of the MLX90614 |
| `sensor_sky_delta` | `true` | calculated from sky temperature and sensor ambient |
| `sensor_cloud_cover` | `true` | calculated from the delta |
| `sensor_wind_speed`, `sensor_wind_gust` | `true` | the two values of the anemometer |
| `sensor_sky_quality`, `sensor_sky_illuminance` | `true` | the two values of the TSL2591 |
| `sensor_sky_luminance` | `true` | calculated from the sky quality |
| `pin_sda`, `pin_scl` | `21`, `22` | I2C pins (BME280, MLX90614 and TSL2591) |
| `i2c_frequency` | `50kHz` | slow on purpose: the sensor head is usually on a long cable |
| `bme280_address` | `"0x76"` | `0x76` (SDO to GND) or `0x77` (SDO to VCC) |
| `mlx90614_address` | `"0x5A"` | factory default |
| `pin_rain` | `25` | input of the rain sensor, `none` if `rain` is false |
| `rain_inverted` | `true` | the module pulls its output LOW when wet (most modules) |
| `pin_wind` | `26` | reed contact, `none` if `wind` is false; needs a pin with a pull-up (not 34 to 39) |
| `wind_filter` | `5ms` | debounce of the reed contact |

### Switching hardware and values off

**Hardware you do not have or do not need:** set its switch (`bme280`, `rain`, `sky`, `wind`, `sqm`) to `false`. Nothing of it is built: its values, the values calculated from it (the dew point from the BME280, the cloud cover from the infrared sensor) and its settings do not exist, and its pins may be `none`. This is the usual case, and the example configurations show it.

**Single values** (optional): every `sensor_...` key switches one value of fitted hardware off. A value that is switched off is not reported to Home Assistant. **What is calculated from it is not built either**:

| Sensor | is built when |
|---|---|
| Temperature, Humidity, Pressure | the group `bme280` and its own switch |
| Dew Point | `sensor_dew_point` and Temperature and Humidity are built |
| Rain | the group `rain` |
| Sky Temperature, Sky Sensor Ambient | the group `sky` and its own switch |
| Sky Temperature Delta | `sensor_sky_delta` and Sky Temperature and Sky Sensor Ambient are built |
| Cloud Cover and its settings (Cloud Clear / Overcast Delta) | `sensor_cloud_cover` and Sky Temperature Delta are built |
| Wind Speed, Wind Gust | the group `wind` and the own switch (each needs only the counter, not the other) |
| Wind settings (pulses per revolution, speed per revolution) | `wind` and at least one of Wind Speed, Wind Gust |
| Sky Quality, Sky Illuminance | `sqm` and the own switch |
| Sky Luminance | `sensor_sky_luminance` and Sky Quality is built |
| Sky Light Counts, Sky Dark Counts, Calibrate Dark Counts, Dark Calibration | the TSL2591 is built (Sky Quality or Sky Illuminance) |
| Sky Quality Offset | Sky Quality is built |

A chip without a sensor that is built is not set up at all: when no sensor on the I2C bus is built there is no I2C bus and the pins `pin_sda`, `pin_scl` may be `none`; the same holds for `pin_wind` when no wind sensor is built. The log line `Built: ...` at the start shows what is built. To only hide a value that something else needs, hide the entity in Home Assistant instead of switching it off here.

### I2C addresses

The addresses of the chips are the keys `bme280_address` and `mlx90614_address`; the TSL2591 has no key.

| Chip | Default | Allowed |
|---|---|---|
| BME280 | `"0x76"` | `"0x76"` or `"0x77"`: the SDO pin of the module selects it (GND = `0x76`, VCC = `0x77`) |
| MLX90614 | `"0x5A"` | any address of the form `"0x.."` if the chip was reprogrammed (this firmware does not reprogram it); not `"0x29"` when the TSL2591 is built |
| TSL2591 | `0x29` | fixed, it cannot be changed |

Write the address **in quotation marks**. Without them YAML reads `0x76` as a number, and the check refuses it.

To find out where a chip answers, set `scan: true` in `esphome-astro-environmental/hardware/hw_esp32_devkit_i2c.yaml` for one flash: at start the device writes every address that answers on the bus to the log. That is also the first thing to try when a sensor stays *unknown*. Set it back to `false` afterwards, the scan is not needed in normal operation. There is one chip of each type on the bus.

### Checks

A wrong value stops the build with an error that names the problem (`CONFIG_ERROR_...` in the message), for example a pin that does not exist or is flash, two functions on one pin, an input-only pin used for I2C or for the reed contact, no sensor built, a switch that is not `true` or `false`, or a wrong I2C address.

## Wiring

| Sensor | Connection |
|---|---|
| BME280 | 3.3 V, GND, SDA = `pin_sda`, SCL = `pin_scl` |
| MLX90614 | 3.3 V, GND, SDA, SCL on the same bus (address `0x5A`) |
| TSL2591 | 3.3 V, GND, SDA, SCL on the same bus (address `0x29`); supply 2.7 to 3.6 V, so use a 3.3 V module |
| Rain sensor module | 3.3 V, GND, digital output (DO) = `pin_rain` |
| Anemometer (reed contact) | one wire to `pin_wind`, the other to GND (the internal pull-up is used) |

## Entities

| Entity | Unit | Meaning |
|---|---|---|
| Temperature | °C | BME280 |
| Humidity | % | BME280 |
| Pressure | hPa | BME280, station pressure (not reduced to sea level) |
| Dew Point | °C | calculated from temperature and humidity |
| Rain | wet / dry | `on` = wet; a drop has to stay 2 s, the state stays wet for 60 s after the last drop |
| Sky Temperature | °C | infrared object temperature of the MLX90614, mean of 60 s |
| Sky Sensor Ambient | °C | temperature of the sensor housing (diagnostic) |
| Sky Temperature Delta | °C | Sky Temperature minus Sky Sensor Ambient |
| Cloud Cover | % | estimated from the delta, see below |
| Wind Speed | km/h | mean of the last 60 s |
| Wind Gust | km/h | maximum of the 3 s values of the last 10 min |
| Sky Quality | mag/arcsec² | TSL2591, one value per minute; unavailable when the chip is saturated (dusk, day) |
| Sky Illuminance | lx | TSL2591, from the same counts |
| Sky Luminance | mcd/m² | calculated from the Sky Quality |
| Sky Light Counts | counts | diagnostic: the mean of one minute (visible channel minus infrared channel), before the dark counts are subtracted |
| Dark Calibration | text | diagnostic: `idle`, `running (n of 10)`, `done: x.x counts` or `failed: ...` |

Settings in Home Assistant (entity category *config*, they survive a restart and a power cut):

| Setting | Default | Meaning |
|---|---|---|
| Cloud Clear Delta | -25 °C | at this delta the sky counts as clear (0 %) |
| Cloud Overcast Delta | -8 °C | at this delta the sky counts as overcast (100 %) |
| Wind Pulses per Revolution | 1 | pulses of the reed contact per revolution |
| Wind Speed per Revolution per Second | 2.4 km/h | speed of one revolution per second (the usual value of the cheap anemometers of the Misol / Froggit / Ecowitt type) |
| Sky Dark Counts | 0 | the counts of the TSL2591 with no light; set by the button below or by hand (0 to 1000) |
| Calibrate Dark Counts | (button) | starts the dark calibration, see [Sky Quality](#sky-quality-sqm) |
| Sky Quality Offset | 0 mag/arcsec² | added to the Sky Quality; brings it to a reference device (-5 to +5) |

Health sensors: Free Heap, Min Free Heap, Uptime, Reset Reason, WiFi RSSI, IP Address, WiFi SSID, WiFi BSSID.

## Calculated Values

**Dew point** (Magnus formula, constants of Sonntag 1990, valid from -45 to +60 °C):

```
gamma = ln(RH / 100) + 17.62 * T / (243.12 + T)
Td    = 243.12 * gamma / (17.62 - gamma)
```

No value if the temperature or the humidity is missing or the humidity is 0.

**Cloud cover** is a linear map of the delta between the two limits, limited to 0 to 100 %:

```
Cloud Cover = clamp((Delta - Clear) / (Overcast - Clear) * 100, 0, 100)
```

How far a clear sky falls below the ambient depends on the sensor's field of view, the humidity and the place, so the two limits are settings in Home Assistant and have to be calibrated against your own observations. Moving both limits moves the whole curve (season), changing their distance changes the slope. With equal limits or Clear above Overcast there is no value (the entity is unavailable) instead of a wrong one. The raw `Sky Temperature Delta` stays visible for the calibration.

**Wind speed**:

```
revolutions per minute = pulses per minute / pulses per revolution
speed (km/h)           = revolutions per second * "Wind Speed per Revolution per Second"
```

After 10 s without a pulse the speed is 0.

## Sky Quality (SQM)

The optional TSL2591 (`sqm: true`) measures how bright the night sky is. Unlike the lens-and-filter Sky Quality Meter it is a bare light sensor, so what it reports is an estimate that has to be calibrated; read the limits below before relying on it.

**What it does.** The chip runs at its highest sensitivity (gain 9500x, integration time 600 ms) all the time. Both channels (visible plus infrared, infrared) are read every second; the valid readings of one minute are averaged, which gives one value per minute and lowers the random noise by about the square root of the number of readings. Averaging does not remove the dark counts, which is why they are a setting:

```
V   = CH0 - CH1                                  mean of one minute   (Sky Light Counts)
E   = (V - dark) / (600 * 9500 / (53 * 7.7))     lx                   (Sky Illuminance)
m   = -2.5 * log10(E / (pi * 1.08e5)) + offset   mag/arcsec2          (Sky Quality)
L   = 1000 * 1.08e5 * 10^(-0.4 * m)              mcd/m2               (Sky Luminance)
```

The sky is taken as a uniformly bright hemisphere (`L = E / pi`) and `L [cd/m2] = 1.08e5 * 10^(-0.4 m)` is the conversion of Unihedron. The offset takes up everything that differs: a window, a diffuser or a filter in front of the chip, the sensitivity of the individual chip and the approximation of the hemisphere.

**By day and at dusk the chip is saturated.** At this sensitivity it is full somewhere around a few lux (the exact value depends on the chip). A saturated reading is not a value: Sky Quality, Sky Illuminance and Sky Luminance are unavailable until the sky is dark again. That is intended, and the datasheet names no illuminance limit that could harm the chip. A lamp that shines on the sensor saturates it as well, so shield it.

**Dark calibration** (once after mounting, again when the temperature range changes):

1. Cover the sensor so that no light reaches it (a cap, black tape), at the place and, if possible, at the temperature of the measurement.
2. Press **Calibrate Dark Counts** in Home Assistant. *Dark Calibration* shows `running (n of 10)`.
3. After about 11 minutes the mean of ten one-minute values is stored in **Sky Dark Counts** and *Dark Calibration* shows `done: x.x counts`. The minute that was running when you pressed the button is discarded.
4. Take the cover off.

The calibration stops with a message if a minute is saturated (`failed: sensor saturated, is it covered?`) or if the mean is above 120 counts (`failed: more than 120 counts, light leak?`). The datasheet gives 0 to 20 counts at 100 ms; at 600 ms that is at most about 120. Without a dark calibration the dark counts are read as light and the sky looks too bright. You can also enter *Sky Dark Counts* by hand.

**Offset.** Put the station next to a reference device (for example a Sky Quality Meter) under the same sky and change **Sky Quality Offset** until the values agree; check it at two brightnesses. Moving the offset by 0.1 mag/arcsec² scales the light by 10 %.

**Limits** (calculated from the datasheet, not measured on a device yet):

- **Where it is useful.** About up to SQM 20.3 (Bortle 5, a suburban sky) the signal is far above the noise and the dark counts. From Bortle 4 downwards (SQM above about 20.8) the dark counts of the individual chip and their drift with the temperature decide: the datasheet gives 0 to 20 counts at 100 ms at 25 °C, no typical value and no temperature curve, and a dark rural sky is only about 8 to 20 counts of signal. There it is good for trends and changes (clouds, moon, twilight, the haze of a light dome), not for absolute values.
- **Accuracy.** Even with calibration expect a few tenths of a magnitude in absolute terms; a Sky Quality Meter is specified to 0.1 mag/arcsec² per device.
- **Field of view.** The chip has a cosine response over the whole hemisphere; a Sky Quality Meter looks at about 20 degrees around the zenith. Horizon glow, trees and buildings add to the reading, so the same sky gives a different value than on a Sky Quality Meter, and the offset is only valid for the sky it was set under.
- **Spectrum.** The chip responds up to 1100 nm; the infrared is subtracted with the second channel, but airglow and the lamps of different types still weigh differently than they do for the eye or for a Sky Quality Meter with its infrared filter.
- **Temperature.** The chip is specified from -30 to 70 °C; a closed enclosure in the sun can be hotter than that, and the dark counts rise with the temperature.
- Averaging helps against random noise only. A longer averaging time does not help the dark counts and smears clouds; one minute is fixed.

## Hardware Notes

- The MLX90614 comes in several fields of view (for example 90°, 35°, 5°). For the sky a narrow field of view is common. It has to look through nothing that blocks infrared (normal glass does).
- Mount the BME280 in a radiation shield and away from the ESP32, which heats up.
- Long cables to the sensor head: keep the I2C frequency low, and add an RC filter (for example 10 kΩ and 100 nF) at the reed contact input.
- The rain sensor module has to give a clean digital level. An open-drain output needs a pull-up resistor.
- The TSL2591 module has to run from 3.3 V (the chip allows 2.7 to 3.6 V). Keep it out of direct light from lamps and give it a clear view of the sky; a window or diffuser in front of it only changes the offset.
- Not tested on a real device yet: measured values, wiring and the calibration of the cloud limits, the wind factor, the dark counts and the sky quality offset are yours to verify.

## Network

WiFi (`esphome-astro-environmental/network/wifi.yaml`). The credentials are secrets. DHCP is the default; for a fixed address reserve one in your router or enable `manual_ip` in the network file and add `static_ip`, `gateway` and `subnet` to `secrets.yaml`.

## Secrets

Copy `secrets.yaml.example` to `secrets.yaml` (ignored by git) and replace every value. The keys `api_encryption_key`, `web_username`, `web_password`, `wifi_ssid` and `wifi_password` must **also** exist in `/config/esphome/secrets.yaml` on Home Assistant: the firmware is built there from those values, and without them the ESPHome dashboard stops with "Secret '<name>' not defined". That file is shared by every device of the dashboard, so devices that use the same key names share the values.

## OTA Updates and ESPHome Version

ESPHome 2026.9.0 or newer is required (encrypted OTA with the key of the API). Regular updates go through the ESPHome dashboard. The web upload in the web interface is the emergency fallback only.

## Deployment

1. Copy `scripts/deployconf` to `scripts/deployconf.secrets` (ignored by git) and fill in `SSH_URL` (the SSH add-on of Home Assistant), `SSH_USER` and optionally `SSH_PW`.
2. `.\scripts\deploy.ps1 -DryRun` shows the target and the files without connecting.
3. `.\scripts\deploy.ps1` copies `esphome-astro-environmental` and `astro-environmental.yaml` to `/config/esphome/` via SCP. `.\scripts\build_and_deploy.ps1` compiles locally first and deploys only when that succeeds.
4. In the ESPHome dashboard, click **Install** on `astro-environmental`.

## Bundle for the ESPHome Device Builder

A bundle (`astro-environmental.esphomebundle.tar.gz`) holds the whole project and can be imported in the ESPHome
Device Builder instead of copying the files by hand. It is attached to a release; the **Build ESPHome bundle** workflow
(GitHub, Actions, Build ESPHome bundle, Run workflow) creates it and attaches it to the latest release (or to the tag that is
entered), and replaces an older file of the same name. The workflow only runs when you start it.

- **No secrets inside.** `esphome bundle` packs the values of the secrets a configuration uses, so
  `scripts/make_bundle.py` removes them again. The keys of `secrets.yaml.example` have to exist in the secrets of
  your Device Builder; the import only adds missing keys and never changes existing ones.
- **All files of the project inside**, not only those the default configuration loads: a configuration that you
  change after the import (hardware switched off, for example) finds the files it needs. The example
  configurations are inside as well.
- The same file is made locally with `python scripts/make_bundle.py` (needs ESPHome); the output goes to `dist/`.

## Tests

`.\scripts\check.ps1` (needs WSL with a Linux distribution; started by hand) compiles the firmware and every example and runs the tests. `-TestsOnly` runs only the tests, `-FirmwareOnly` only the compile.

- `tests/test_config_checks.py`: a wrong configuration fails with the named `CONFIG_ERROR_...`, a right one builds exactly the entities that are built (also for every single switch and for what is calculated from a switched-off sensor), every example validates.
- `tests/test_formulas.py`: dew point (also against the Buck equation), cloud cover, wind speed, sky quality and the rule of the dark calibration, and that the YAML uses the same constants and expressions.
- `tests/test_bundle.py`: the bundle has no secrets, contains every file of the project, can be read by ESPHome, and a configuration changed after the import still validates.

## Web Interface

`http://<name>.local` shows the entities and the logs. It asks for `web_username` and `web_password` (digest authentication).

## License

GPL-3.0, see [LICENSE](LICENSE).
