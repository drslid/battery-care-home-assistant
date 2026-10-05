import { describe, expect, it } from "vitest";
import {
  formatBattery,
  formatLevel,
  formatRelative,
  intlLocale,
} from "../src/format";

const NOW = Date.parse("2026-10-05T12:00:00Z");
const HOUR = 3600 * 1000;

describe("formatters", () => {
  it("accept Home Assistant language tags", () => {
    expect(intlLocale("fr-CA")).toBe("fr-CA");
    expect(intlLocale("en_GB!")).toBe("en");
    expect(intlLocale(undefined)).toBe("en");
  });

  it("show levels as whole percentages in the user's language", () => {
    expect(formatLevel(8, "en")).toBe("8%");
    expect(formatLevel(77.6, "en")).toBe("78%");
    // The space before % depends on the ICU version; the locale must apply.
    expect(formatLevel(8, "fr")).toBe(
      new Intl.NumberFormat("fr", { style: "percent" }).format(0.08),
    );
    expect(formatLevel(8, "fr")).not.toBe("8%");
  });

  it("show the quantity of batteries only when there are several", () => {
    expect(formatBattery({ type: "CR2032", quantity: 1 }, "en")).toBe("CR2032");
    expect(formatBattery({ type: "CR123A", quantity: 2 }, "fr")).toBe(
      "2 × CR123A",
    );
  });

  it("say how long ago something happened", () => {
    const at = (offset: number) => new Date(NOW - offset);
    expect(formatRelative(at(10 * 1000), "en", NOW)).toBe("now");
    expect(formatRelative(at(5 * 60 * 1000), "en", NOW)).toBe("5 minutes ago");
    expect(formatRelative(at(3 * HOUR), "en", NOW)).toBe("3 hours ago");
    expect(formatRelative(at(3 * HOUR), "fr", NOW)).toBe("il y a 3 heures");
    expect(formatRelative(at(24 * HOUR), "en", NOW)).toBe("yesterday");
    expect(formatRelative(at(18 * 24 * HOUR), "en", NOW)).toBe("18 days ago");
    expect(formatRelative(at(90 * 24 * HOUR), "en", NOW)).toBe("3 months ago");
    expect(formatRelative(at(800 * 24 * HOUR), "en", NOW)).toBe("2 years ago");
  });
});
