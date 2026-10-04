# Battery Care for Home Assistant

**Smart Battery Management for Home Assistant.** Never worry about your smart home batteries again.

> [!IMPORTANT]
> Battery Care is in early development and not ready for use yet. This page will explain how to install it once the first test release is available.

Battery Care is a zero-config battery monitoring and maintenance experience for Home Assistant. It automatically discovers battery-powered devices, highlights what needs attention, and handles low-battery alerts without requiring YAML or custom automations.

## What it will do

- **Find every battery automatically**, whichever integration provides it (Zigbee, Z-Wave, Matter, Bluetooth, ESPHome and more), without duplicates.
- **Show what needs attention first**, in a dashboard in the sidebar that works on phones and desktops, in light and dark mode.
- **Alert you without automations**: low and critical levels, devices that stop responding, reminders, snooze and quiet hours.
- **Track replacements**: battery type and quantity, replacement history, and a check that the new battery is detected.
- **Work with [Battery Notes](https://github.com/andrew-codechimp/HA-Battery-Notes)** when it is installed, without requiring it.

## Requirements

- Home Assistant 2026.8 or later.

## Privacy

Battery Care runs entirely inside Home Assistant. It sends no telemetry and loads nothing from the internet.

## License

[MIT](LICENSE)

Battery Care is an independent project. It is not affiliated with or endorsed by Home Assistant or the Open Home Foundation.
