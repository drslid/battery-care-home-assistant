import {
  mdiBattery,
  mdiBattery10,
  mdiBattery20,
  mdiBattery30,
  mdiBattery40,
  mdiBattery50,
  mdiBattery60,
  mdiBattery70,
  mdiBattery80,
  mdiBattery90,
  mdiBatteryAlertVariantOutline,
  mdiBatteryCharging,
  mdiBatteryLow,
  mdiBatteryOutline,
  mdiBatteryUnknown,
  mdiBellOffOutline,
  mdiLanDisconnect,
} from "@mdi/js";
import { html, type TemplateResult } from "lit";
import type { DeviceView, Status } from "./api";

const LEVEL_ICONS = [
  mdiBatteryOutline,
  mdiBattery10,
  mdiBattery20,
  mdiBattery30,
  mdiBattery40,
  mdiBattery50,
  mdiBattery60,
  mdiBattery70,
  mdiBattery80,
  mdiBattery90,
  mdiBattery,
];

const STATUS_ICONS: Record<Exclude<Status, "ok">, string> = {
  critical: mdiBatteryAlertVariantOutline,
  low: mdiBatteryLow,
  not_responding: mdiLanDisconnect,
  charging: mdiBatteryCharging,
  unknown: mdiBatteryUnknown,
  ignored: mdiBellOffOutline,
};

/** Return the battery icon that shows a level, in steps of ten. */
export function levelIcon(level: number | null): string {
  if (level === null) {
    return mdiBatteryUnknown;
  }
  const step = Math.min(10, Math.max(0, Math.round(level / 10)));
  return LEVEL_ICONS[step] ?? mdiBattery;
}

export function statusIcon(
  device: Pick<DeviceView, "status" | "level">,
): string {
  return device.status === "ok"
    ? levelIcon(device.level)
    : STATUS_ICONS[device.status];
}

export type Tone = "error" | "warning" | "muted" | "default";

/** Colour is only for what needs attention; a device without data is muted. */
export function statusTone(
  device: Pick<DeviceView, "status" | "attention">,
): Tone {
  if (device.attention) {
    return device.status === "critical" ? "error" : "warning";
  }
  return device.status === "unknown" ? "muted" : "default";
}

/** Draw a Material Design icon; the text next to it carries the meaning. */
export function icon(path: string): TemplateResult {
  return html`<svg
    class="icon"
    viewBox="0 0 24 24"
    aria-hidden="true"
    focusable="false"
  >
    <path d=${path}></path>
  </svg>`;
}
