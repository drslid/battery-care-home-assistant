import { describe, expect, it } from "vitest";
import { localize, resolveLanguage } from "../src/i18n";
import en from "../src/translations/en.json";
import fr from "../src/translations/fr.json";

function keys(node: unknown, prefix = ""): string[] {
  if (typeof node !== "object" || node === null) {
    return [prefix];
  }
  return Object.entries(node).flatMap(([name, child]) =>
    keys(child, prefix ? `${prefix}.${name}` : name),
  );
}

describe("translations", () => {
  it("define the same keys in every language", () => {
    expect(keys(fr).sort()).toEqual(keys(en).sort());
  });

  it("map Home Assistant language tags to a bundled language", () => {
    expect(resolveLanguage("fr-CA")).toBe("fr");
    expect(resolveLanguage("FR")).toBe("fr");
    expect(resolveLanguage("de")).toBe("en");
    expect(resolveLanguage(undefined)).toBe("en");
  });

  it("fall back to English, then to the key", () => {
    expect(localize("fr", "nav.all")).toBe("Toutes les batteries");
    expect(localize("fr", "panel.missing")).toBe("panel.missing");
    expect(localize("en", "panel")).toBe("panel");
  });

  it("choose the plural form from the count", () => {
    const key = "overview.attention_title";
    expect(localize("en", key, { count: 1 })).toBe("1 battery needs attention");
    expect(localize("en", key, { count: 1200 })).toBe(
      "1,200 batteries need attention",
    );
    // French uses the singular for zero.
    expect(localize("fr", key, { count: 0 })).toBe(
      "0 batterie demande votre attention",
    );
    expect(localize("fr", key, { count: 2 })).toBe(
      "2 batteries demandent votre attention",
    );
    expect(localize("en", key)).toBe(key);
  });

  it("fill in parameters and keep unknown placeholders", () => {
    expect(
      localize("en", "alerts.automatic", { low: "20%", critical: "10%" }),
    ).toBe("Automatic · low at 20%, critical at 10%");
    expect(localize("en", "alerts.automatic", { low: "20%" })).toBe(
      "Automatic · low at 20%, critical at {critical}",
    );
  });
});
