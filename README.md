# Battery Care for Home Assistant

**Smart Battery Management for Home Assistant.** Never worry about your smart home batteries again.

> [!IMPORTANT]
> Battery Care 0.1 is a first test release. It finds your batteries and shows them in the sidebar, but it does not send alerts yet. Please [report](https://github.com/drslid/battery-care-home-assistant/issues) any battery that is missing, duplicated or shown with the wrong status.

Battery Care is a zero-config battery monitoring and maintenance experience for Home Assistant. It automatically discovers battery-powered devices, highlights what needs attention, and handles low-battery alerts without requiring YAML or custom automations.

## In this test release

- Battery-powered devices are found automatically and followed live, including new ones.
- A **Battery Care** panel in the sidebar shows what needs attention first, then every battery, with details for each device.
- English and French.

## What it will do

- **Find every battery automatically**, whichever integration provides it (Zigbee, Z-Wave, Matter, Bluetooth, ESPHome and more), without duplicates.
- **Show what needs attention first**, in a dashboard in the sidebar that works on phones and desktops, in light and dark mode.
- **Alert you without automations**: low and critical levels, devices that stop responding, reminders, snooze and quiet hours.
- **Track replacements**: battery type and quantity, replacement history, and a check that the new battery is detected.
- **Work with [Battery Notes](https://github.com/andrew-codechimp/HA-Battery-Notes)** when it is installed, without requiring it.

## Requirements

- Home Assistant 2026.8 or later.

## Installation

### With HACS

1. In HACS, open the menu in the top right corner and select **Custom repositories**.
2. Add `https://github.com/drslid/battery-care-home-assistant` with the type **Integration**.
3. Search for **Battery Care** in HACS, download it, then restart Home Assistant.
4. Go to **Settings** > **Devices & services** > **Add integration** and select **Battery Care**.

### Manually

1. Download **Source code (zip)** from the [latest release](https://github.com/drslid/battery-care-home-assistant/releases/latest).
2. Copy its `custom_components/battery_care` folder into the `custom_components` folder of your Home Assistant configuration, then restart Home Assistant.
3. Go to **Settings** > **Devices & services** > **Add integration** and select **Battery Care**.

Battery Care then appears in the sidebar for every user.

## Privacy

Battery Care runs entirely inside Home Assistant. It sends no telemetry and loads nothing from the internet.

## License

[MIT](LICENSE)

Battery Care is an independent project. It is not affiliated with or endorsed by Home Assistant or the Open Home Foundation.
