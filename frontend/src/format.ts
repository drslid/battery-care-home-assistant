import type { Battery } from "./api";

/** Return a locale tag that `Intl` accepts, or English. */
export function intlLocale(tag: string | undefined): string {
  try {
    return Intl.getCanonicalLocales(tag)[0] ?? "en";
  } catch {
    return "en";
  }
}

// Building formatters is slow next to using them; long lists reuse them.
const formatters = new Map<
  string,
  Intl.NumberFormat | Intl.RelativeTimeFormat
>();

function cached<T extends Intl.NumberFormat | Intl.RelativeTimeFormat>(
  key: string,
  create: () => T,
): T {
  let formatter = formatters.get(key);
  if (formatter === undefined) {
    formatter = create();
    formatters.set(key, formatter);
  }
  return formatter as T;
}

/** Format a battery level, such as 8 % or 78%, without decimals. */
export function formatLevel(level: number, locale: string): string {
  return cached(
    `percent:${locale}`,
    () =>
      new Intl.NumberFormat(locale, {
        style: "percent",
        maximumFractionDigits: 0,
      }),
  ).format(level / 100);
}

/** Format a battery type with its quantity, such as 2 × CR123A. */
export function formatBattery(battery: Battery, locale: string): string {
  if (battery.quantity <= 1) {
    return battery.type;
  }
  const quantity = cached(
    `number:${locale}`,
    () => new Intl.NumberFormat(locale),
  ).format(battery.quantity);
  return `${quantity} × ${battery.type}`;
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 86400],
  ["month", 30 * 86400],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

/** Format a moment relative to now, such as "3 hours ago". */
export function formatRelative(
  date: Date,
  locale: string,
  now: number = Date.now(),
): string {
  const seconds = (date.getTime() - now) / 1000;
  const format = cached(
    `relative:${locale}`,
    () => new Intl.RelativeTimeFormat(locale, { numeric: "auto" }),
  );
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) {
      return format.format(Math.round(seconds / size), unit);
    }
  }
  return format.format(0, "second");
}
