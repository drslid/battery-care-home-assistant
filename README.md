# Battery Care for Home Assistant — every battery in one place, without YAML

**Smart Battery Management for Home Assistant.** Never worry about your smart home batteries again.

Battery Care finds every **battery-powered device** in Home Assistant on its own, whichever integration provides it: Zigbee, Z-Wave, Matter, Bluetooth, ESPHome and more. A **battery dashboard** in the sidebar shows what needs attention first, on your phone or your computer. No YAML, no template sensors, no automations to write, and nothing leaves your home.

> [!IMPORTANT]
> Battery Care 0.1 is a first test release: it finds your batteries and shows them in the sidebar, but it does not send alerts yet. Please [report](https://github.com/drslid/battery-care-home-assistant/issues) any battery that is missing, duplicated or shown with the wrong status.

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=drslid&repository=battery-care-home-assistant&category=integration)
[![Open your Home Assistant instance and start setting up Battery Care.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=battery_care)

## ✨ What it does

- 🔍 **Finds every battery** — battery levels, low-battery warnings and charging sensors are grouped per device, without duplicates: copies made by Battery Notes or by helpers such as groups and statistics are skipped.
- 🚨 **Shows what needs attention first** — the most urgent batteries come first, then every battery from the lowest level, with a detail sheet for each device.
- 🔄 **Stays up to date** — levels change live, and new devices appear on their own.
- 📱 **Knows what you recharge** — phones, robot vacuums and mowers are shown, and so are batteries you do not maintain yourself, such as a car, a UPS or a home battery, but they never count as needing attention.
- 🏷️ **Works with [Battery Notes](https://github.com/andrew-codechimp/HA-Battery-Notes)** — when it is installed, the battery type and quantity come from it. It is not required.
- 🌍 **English and French**, in light and dark mode.

## 🗺️ Roadmap

- **0.2 — Alerts:** low and critical batteries, devices that stop responding or stop reporting, reminders, snooze and quiet hours, delivered to Home Assistant and to your phone. A health score and summary sensors for your own dashboards and automations.
- **0.3 — Your settings and replacements:** thresholds per device, devices to ignore, battery type and quantity, replacement history, and a check that the new battery is detected.
- **1.0** — Submitted to the default HACS list, so that it can be found without adding the repository.

## 🚀 Install in 4 steps

1. In **HACS**, open the ⋮ menu → **Custom repositories**, add `https://github.com/drslid/battery-care-home-assistant` with the type **Integration** (or use the HACS button above).
2. Search for **Battery Care** in HACS and select **Download**.
3. **Restart** Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Battery Care** (or use the second button above) and confirm. No YAML, no option required.

Requires Home Assistant **2026.8** or newer.

Without HACS: download **Source code (zip)** from the [latest release](https://github.com/drslid/battery-care-home-assistant/releases/latest), copy its `custom_components/battery_care` folder into the `custom_components` folder of your Home Assistant configuration, restart, then follow step 4.

## 📲 Usage

Open **Battery Care** in the sidebar. It is there for every user.

- **Overview** — how many batteries need attention, and which ones, most urgent first.
- **All batteries** — every battery, problems first, then from the lowest level.
- **Device sheet** — tap a battery to see its level, status, battery type, last report, category and importance, and the entities Battery Care reads.

| Status           | Meaning                                            |
| ---------------- | -------------------------------------------------- |
| Battery critical | 10 % or less.                                      |
| Battery low      | 20 % or less, or the device reports a low battery. |
| Not responding   | Its battery entities are unavailable.              |
| Charging         | The device is charging.                            |
| No data yet      | The device has not reported a usable value yet.    |
| OK               | None of the above.                                 |

## ❓ FAQ

**Which batteries does it find?**
Every sensor with the _battery_ device class in %, and every binary sensor that reports a low battery or charging, whatever the integration. They are grouped per device.

**Why is my phone not in "Needs attention"?**
Phones, tablets and other devices you recharge every day would nag you all the time. Battery Care shows their level but does not count them as needing attention.

**Does it replace Battery Notes?**
No, they work together. Battery Notes remains the place to record battery types; Battery Care reads them and ignores the copies of battery sensors that Battery Notes creates.

**A battery is missing or shown twice. What should I do?**
[Open an issue](https://github.com/drslid/battery-care-home-assistant/issues) with the name of the integration that provides the device, and the device class and unit of its battery entity.

**Does it send data anywhere?**
No. Battery Care runs entirely inside Home Assistant: no cloud, no telemetry, and the panel loads nothing from the internet.

## ⚠️ Known limitations

- No alerts or notifications yet: they arrive with 0.2.
- The thresholds are fixed at 20 % for low and 10 % for critical until the settings arrive with 0.3.
- Devices are found automatically; you cannot add or ignore one by hand yet.

## 🛠️ Development

```bash
scripts/setup    # Python environments with the Home Assistant test harness, and the frontend packages
scripts/test     # pytest with coverage (--min for the oldest supported Home Assistant), then the frontend tests
scripts/lint     # ruff, mypy, ESLint, Prettier and TypeScript
scripts/develop  # a local Home Assistant on http://localhost:8123 with Battery Care linked in
```

The panel is built with `npm run --prefix frontend build`. The bundle is committed, and CI checks that it matches the sources.

## Trademark

Battery Care is an independent project, not affiliated with or endorsed by Home Assistant or the Open Home Foundation. Home Assistant is a trademark of the Open Home Foundation.

## License

[MIT](LICENSE)
