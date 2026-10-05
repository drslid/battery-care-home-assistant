import {
  mdiBattery,
  mdiBattery50,
  mdiBatteryAlertVariantOutline,
  mdiBatteryCharging,
  mdiBatteryLow,
  mdiBatteryOutline,
  mdiBatteryUnknown,
  mdiBellOffOutline,
  mdiClockAlertOutline,
  mdiLanDisconnect,
} from "@mdi/js";
import { describe, expect, it } from "vitest";
import { levelIcon, statusIcon, statusTone } from "../src/status";

describe("status display", () => {
  it("draws the level in steps of ten", () => {
    expect(levelIcon(null)).toBe(mdiBatteryUnknown);
    expect(levelIcon(0)).toBe(mdiBatteryOutline);
    expect(levelIcon(47)).toBe(mdiBattery50);
    expect(levelIcon(100)).toBe(mdiBattery);
  });

  it("uses the icons of the specification", () => {
    const icon = (status: Parameters<typeof statusIcon>[0]["status"]) =>
      statusIcon({ status, level: 50 });
    expect(icon("critical")).toBe(mdiBatteryAlertVariantOutline);
    expect(icon("low")).toBe(mdiBatteryLow);
    expect(icon("not_responding")).toBe(mdiLanDisconnect);
    expect(icon("stale")).toBe(mdiClockAlertOutline);
    expect(icon("charging")).toBe(mdiBatteryCharging);
    expect(icon("unknown")).toBe(mdiBatteryUnknown);
    expect(icon("ignored")).toBe(mdiBellOffOutline);
    expect(icon("ok")).toBe(mdiBattery50);
  });

  it("keeps colour for what needs attention", () => {
    expect(statusTone({ status: "critical", attention: true })).toBe("error");
    expect(statusTone({ status: "low", attention: true })).toBe("warning");
    expect(statusTone({ status: "not_responding", attention: true })).toBe(
      "warning",
    );
    // A rechargeable device at 5 % is shown, but alerts are off for it.
    expect(statusTone({ status: "critical", attention: false })).toBe(
      "default",
    );
    expect(statusTone({ status: "unknown", attention: false })).toBe("muted");
    expect(statusTone({ status: "stale", attention: false })).toBe("secondary");
  });
});
