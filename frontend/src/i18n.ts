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

function lookup(catalog: unknown, key: string): unknown {
  let node = catalog;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null || !hasOwn(node, part)) {
      return undefined;
    }
    node = (node as Record<string, unknown>)[part];
  }
  return node;
}

const pluralRules = new Map<Language, Intl.PluralRules>();

/** Return the text of a catalogue entry; plural entries need a count. */
function text(
  node: unknown,
  language: Language,
  count: number | undefined,
): string | undefined {
  if (typeof node === "string") {
    return node;
  }
  if (count === undefined || typeof node !== "object" || node === null) {
    return undefined;
  }
  let rules = pluralRules.get(language);
  if (rules === undefined) {
    rules = new Intl.PluralRules(language);
    pluralRules.set(language, rules);
  }
  const forms = node as Record<string, unknown>;
  const category = rules.select(count);
  const form = hasOwn(forms, category) ? forms[category] : forms.other;
  return typeof form === "string" ? form : undefined;
}

export type Params = Record<string, string | number>;

/**
 * Translate a dotted key, falling back to English, then to the key itself.
 *
 * `{name}` placeholders take the matching parameter. A numeric `count`
 * parameter selects the plural form, as `Intl.PluralRules` names them.
 */
export function localize(
  language: Language,
  key: string,
  params?: Params,
): string {
  const count = typeof params?.count === "number" ? params.count : undefined;
  const template =
    text(lookup(catalogs[language], key), language, count) ??
    text(lookup(catalogs.en, key), "en", count) ??
    key;
  if (params === undefined) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (placeholder, name: string) => {
    if (!hasOwn(params, name)) {
      return placeholder;
    }
    const value = params[name];
    return typeof value === "number"
      ? new Intl.NumberFormat(language).format(value)
      : String(value);
  });
}
