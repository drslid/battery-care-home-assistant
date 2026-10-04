import en from "./translations/en.json";
import fr from "./translations/fr.json";

const catalogs = { en, fr } satisfies Record<string, typeof en>;

export type Language = keyof typeof catalogs;

function hasOwn(node: object, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(node, key);
}

function isLanguage(value: string): value is Language {
  return hasOwn(catalogs, value);
}

/** Map a Home Assistant language tag such as "fr-CA" to a bundled catalogue. */
export function resolveLanguage(tag: string | undefined): Language {
  const base = tag?.toLowerCase().split("-")[0] ?? "";
  return isLanguage(base) ? base : "en";
}

function lookup(catalog: unknown, key: string): string | undefined {
  let node = catalog;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null || !hasOwn(node, part)) {
      return undefined;
    }
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

/** Translate a dotted key, falling back to English, then to the key itself. */
export function localize(language: Language, key: string): string {
  return lookup(catalogs[language], key) ?? lookup(catalogs.en, key) ?? key;
}
