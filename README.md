# Battery Care for Home Assistant — every battery in one place, without YAML

**Smart Battery Management for Home Assistant.** Never worry about your smart home batteries again.

Battery Care finds every **battery-powered device** in Home Assistant on its own, whichever integration provides it: Zigbee, Z-Wave, Matter, Bluetooth, ESPHome and more. A **battery dashboard** in the sidebar shows what needs attention first, and Battery Care **tells you when a battery needs changing**, in Home Assistant and on your phone. No YAML, no template sensors, no automations to write, and no cloud service of its own.

> [!IMPORTANT]
> Battery Care 0.2 is a test release. Please [report](https://github.com/drslid/battery-care-home-assistant/issues) any battery that is missing, duplicated or shown with the wrong status, and any alert that comes too early, too late or not at all.

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=drslid&repository=battery-care-home-assistant&category=integration)
[![Open your Home Assistant instance and start setting up Battery Care.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=battery_care)

## ✨ What it does

- 🔍 **Finds every battery** — battery levels, low-battery warnings and charging sensors, but also the `battery_level` attribute of older integrations, text states such as _low_ or _full_, and percentage sensors named like a battery. They are grouped per device, without duplicates: copies made by Battery Notes or by helpers such as groups and statistics are skipped.
- 🔔 **Tells you when to change a battery** — a critical battery is notified at once; low batteries, devices that stop responding or stop reporting, and batteries back to normal come in one daily summary. Quiet hours keep the night silent.
- 🗂️ **Every kind of battery, with its own rules** — replaceable, rechargeable, robot, vehicle, UPS, home battery or unknown, each with its own alerts and thresholds. Phones, robot vacuums, cars and home batteries are shown, but they do not alert you unless you turn their type on.
- 🎛️ **Adjust any battery** — from its sheet, change its type or importance, give it its own thresholds, snooze its notifications for a few days, or ignore it.
- 🚨 **Shows what needs attention first** — the most urgent batteries come first, then every battery from the lowest level, with a detail sheet for each device.
- 🔄 **Stays up to date** — levels change live, and new devices appear on their own.
- 📊 **Ready for your dashboards and automations** — a battery health score, the counts of low, critical and monitored batteries, an _Attention required_ sensor, and `battery_care_alert` and `battery_care_recovered` events.
- 🏷️ **Works with [Battery Notes](https://github.com/andrew-codechimp/HA-Battery-Notes)** — when it is installed, the battery type and quantity come from it. It is not required.
- 🌍 **English and French**, in light and dark mode.

## 🗺️ Roadmap

- **0.3 — Dashboard and replacements:** search, filters and grouping by area, the battery type and quantity on the sheet, batteries that only report a voltage, and a replacement history with a check that the new battery is detected.
- **1.0** — Submitted to the default HACS list, so that it can be found without adding the repository.

## 🚀 Install in 4 steps

1. In **HACS**, open the ⋮ menu → **Custom repositories**, add `https://github.com/drslid/battery-care-home-assistant` with the type **Integration** (or use the HACS button above).
2. Search for **Battery Care** in HACS and select **Download**.
3. **Restart** Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Battery Care** (or use the second button above). Choose the phones to notify, the time of the daily summary and the quiet hours, or keep the defaults and confirm. No YAML.

Requires Home Assistant **2026.8** or newer.

Without HACS: download **Source code (zip)** from the [latest release](https://github.com/drslid/battery-care-home-assistant/releases/latest), copy its `custom_components/battery_care` folder into the `custom_components` folder of your Home Assistant configuration, restart, then follow step 4.

## 📲 Usage

Open **Battery Care** in the sidebar. It is there for every user.

- **Overview** — how many batteries need attention, and which ones, most urgent first.
- **All batteries** — every battery, problems first, then from the lowest level.
- **Device sheet** — tap a battery to see its level, status, battery type, last report, category and importance, and the entities Battery Care reads. When it needs attention, anyone can snooze its notifications; administrators can change its type, importance and thresholds, or ignore it.
- **Settings** — alerts and thresholds per battery type, notifications, reminders and delays, and the ignored batteries. Only administrators can change them.

| Status               | Meaning                                                                                           |
| -------------------- | ------------------------------------------------------------------------------------------------- |
| Battery critical     | At or below the critical threshold of its type (10 % by default), or reported as empty.           |
| Battery low          | At or below the low threshold of its type (20 % by default), or the device reports a low battery. |
| Not responding       | Its battery entities have been unavailable for a while (24 hours by default).                     |
| Data may be outdated | No battery report for a while (7 days by default).                                                |
| Charging             | The device is charging.                                                                           |
| No data yet          | The device has not reported a usable value yet.                                                   |
| Alerts off           | You chose to ignore this battery.                                                                 |
| OK                   | None of the above.                                                                                |

UPS batteries are low at 50 % and critical at 20 %, home batteries at 10 % and 5 %. Alerts are on by default for replaceable, UPS and unknown batteries.

## 🔔 Notifications

- **At once:** a battery that becomes critical.
- **In the daily summary**, at 18:00 by default: low batteries, devices that stop responding or stop reporting, batteries back to normal, and reminders for batteries that still need attention.
- **Quiet hours**, from 22:00 to 08:00 by default: nothing is sent, not even a critical battery; what was held is sent when they end.
- **Where:** in Home Assistant notifications, and on the phones and tablets with the [Home Assistant app](https://companion.home-assistant.io/) that you choose. Tapping a phone notification opens Battery Care.
- **Check it:** Settings → Notifications → **Send a test notification**.
- **Your own automations:** every alert fires a `battery_care_alert` event with the device, its area, the severity and the level, and every recovery fires a `battery_care_recovered` event.

## ❓ FAQ

**Which batteries does it find?**
Every sensor with the _battery_ device class in %, every binary sensor that reports a low battery or charging, the `battery_level` attribute of other entities, text states such as _low_ or _full_, and percentage sensors named like a battery, whatever the integration. They are grouped per device.

**Why does my phone never alert me?**
Phones, tablets, robot vacuums, cars and home batteries are recharged on their own, so their alerts are off by default. Turn them on in **Settings → Alerts by battery type**, or give one device another type from its sheet.

**How do I stop the alerts for one battery?**
Open it and choose **Ignore this battery**: it stays in the list but never alerts. To pause its notifications for a few days only, use **Snooze notifications**.

**My phone receives nothing.**
Check that it is chosen in **Settings → Notifications**, then send a test notification. A phone is listed once the Home Assistant app is installed and signed in to this Home Assistant.

**Does it replace Battery Notes?**
No, they work together. Battery Notes remains the place to record battery types; Battery Care reads them and ignores the copies of battery sensors that Battery Notes creates.

**A battery is missing or shown twice. What should I do?**
[Open an issue](https://github.com/drslid/battery-care-home-assistant/issues) with the name of the integration that provides the device, and the device class and unit of its battery entity.

**Does it send data anywhere?**
Battery Care has no cloud service and no telemetry, and the panel loads nothing from the internet. Phone notifications are delivered by the Home Assistant app, like any other Home Assistant notification.

## ⚠️ Known limitations

- Batteries that only report a voltage are not read yet: they need the battery type, which arrives with 0.3.
- Notifications go to Home Assistant and to phones with the Home Assistant app. For other services, such as Telegram or email, use the `battery_care_alert` event in an automation.
- Devices are found automatically; you cannot add one by hand.

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
