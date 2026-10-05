import { html, nothing, type TemplateResult } from "lit";
import { repeat } from "lit/directives/repeat.js";
import type { DeviceView, Importance, Status, Summary } from "./api";
import { formatBattery, formatLevel } from "./format";
import { localize, type Language } from "./i18n";
import { icon, statusIcon, statusTone } from "./status";

export interface ViewContext {
  language: Language;
  locale: string;
  deviceHref(key: string): string;
}

const SEVERITY: Partial<Record<Status, number>> = {
  critical: 0,
  not_responding: 1,
  low: 2,
};
const IMPORTANCE: Record<Importance, number> = {
  critical: 0,
  important: 1,
  normal: 2,
  low: 3,
};

function byName(a: DeviceView, b: DeviceView): number {
  return a.name.localeCompare(b.name);
}

function byLevel(a: DeviceView, b: DeviceView): number {
  // Devices without a level go last.
  const levelA = a.level ?? Number.POSITIVE_INFINITY;
  const levelB = b.level ?? Number.POSITIVE_INFINITY;
  return levelA === levelB ? byName(a, b) : levelA - levelB;
}

/** Most severe first, then the most important, then the lowest level. */
export function byAttention(a: DeviceView, b: DeviceView): number {
  return (
    (SEVERITY[a.status] ?? 3) - (SEVERITY[b.status] ?? 3) ||
    IMPORTANCE[a.importance] - IMPORTANCE[b.importance] ||
    byLevel(a, b)
  );
}

export function sortByLevel(devices: Iterable<DeviceView>): DeviceView[] {
  return [...devices].sort(byLevel);
}

function deviceRow(device: DeviceView, context: ViewContext): TemplateResult {
  const tone = statusTone(device);
  const details = [
    device.area,
    device.battery && formatBattery(device.battery, context.locale),
  ].filter(Boolean);
  return html`<li>
    <a class="row" href=${context.deviceHref(device.key)}>
      <span class="row-icon tone-${tone}">${icon(statusIcon(device))}</span>
      <span class="row-text">
        <span class="row-name">${device.name}</span>
        ${
          details.length
            ? html`<span class="row-details secondary"
                >${details.join(" · ")}</span
              >`
            : nothing
        }
      </span>
      <span class="row-value">
        ${
          device.level === null
            ? nothing
            : html`<span class="row-level"
                >${formatLevel(device.level, context.locale)}</span
              >`
        }
        ${
          device.status === "ok"
            ? nothing
            : html`<span class="row-status ${device.attention ? "strong" : ""}"
                >${localize(context.language, `status.${device.status}`)}</span
              >`
        }
      </span>
    </a>
  </li>`;
}

function deviceRows(
  devices: DeviceView[],
  context: ViewContext,
): TemplateResult {
  return html`<ul class="rows">
    ${repeat(
      devices,
      (device) => device.key,
      (device) => deviceRow(device, context),
    )}
  </ul>`;
}

function summaryTitle(summary: Summary, language: Language): string {
  if (summary.attention > 0) {
    return localize(language, "overview.attention_title", {
      count: summary.attention,
    });
  }
  return localize(
    language,
    summary.monitored > 0
      ? "overview.healthy_title"
      : "overview.no_alerts_title",
  );
}

function count(
  value: number,
  label: string,
  tone: "error" | "warning" | null,
): TemplateResult {
  return html`<div class="count">
    <dt>
      ${value > 0 && tone ? html`<span class="dot tone-${tone}"></span>` : nothing}
      ${label}
    </dt>
    <dd>${value}</dd>
  </div>`;
}

export function renderOverview(
  devices: Iterable<DeviceView>,
  summary: Summary,
  allHref: string,
  context: ViewContext,
): TemplateResult {
  const { language } = context;
  if (summary.total === 0) {
    return html`<section class="card empty">
      <h2>${localize(language, "overview.empty_title")}</h2>
      <p class="secondary">${localize(language, "overview.empty_text")}</p>
    </section>`;
  }
  const attention = [...devices]
    .filter((device) => device.attention)
    .sort(byAttention);
  return html`
    <section class="card summary">
      <div role="status">
        <h2>${summaryTitle(summary, language)}</h2>
      </div>
      <dl class="counts">
        ${count(summary.healthy, localize(language, "counts.healthy"), null)}
        ${count(summary.low, localize(language, "counts.low"), "warning")}
        ${count(
          summary.critical,
          localize(language, "counts.critical"),
          "error",
        )}
        ${count(
          summary.not_responding,
          localize(language, "counts.not_responding"),
          "warning",
        )}
      </dl>
    </section>
    ${
      attention.length
        ? html`<section class="card">
            <h2>${localize(language, "overview.needs_attention")}</h2>
            ${deviceRows(attention, context)}
          </section>`
        : nothing
    }
    <a class="see-all" href=${allHref}>
      ${localize(language, "overview.see_all", { count: summary.total })}
    </a>
  `;
}

export function renderAll(
  devices: Iterable<DeviceView>,
  context: ViewContext,
): TemplateResult {
  const sorted = sortByLevel(devices);
  return html`<section class="card">
    <h2>
      ${localize(context.language, "all.title", { count: sorted.length })}
    </h2>
    ${deviceRows(sorted, context)}
  </section>`;
}

/** Placeholders with the size of the real content, so nothing shifts. */
export function renderSkeleton(message: string): TemplateResult {
  return html`<section class="card" aria-busy="true">
    <p class="visually-hidden" role="status">${message}</p>
    <ul class="rows" aria-hidden="true">
      ${[0, 1, 2].map(
        () =>
          html`<li class="row">
            <span class="skeleton skeleton-icon"></span>
            <span class="row-text">
              <span class="skeleton skeleton-line"></span>
              <span class="skeleton skeleton-line short"></span>
            </span>
          </li>`,
      )}
    </ul>
  </section>`;
}
