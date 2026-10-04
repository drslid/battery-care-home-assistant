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

  it("fall back to the key when nothing matches", () => {
    expect(localize("fr", "panel.starting")).toBe("Démarrage…");
    expect(localize("fr", "panel.missing")).toBe("panel.missing");
    expect(localize("en", "panel")).toBe("panel");
  });
});
