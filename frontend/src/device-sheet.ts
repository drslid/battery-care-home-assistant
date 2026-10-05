import { mdiChevronDown, mdiClose } from "@mdi/js";
import {
  LitElement,
  css,
  html,
  nothing,
  type PropertyValues,
  type TemplateResult,
} from "lit";
import { live } from "lit/directives/live.js";
import type {
  BatteryClass,
  DeviceDetails,
  DeviceMode,
  DeviceView,
  Importance,
  Settings,
  Source,
} from "./api";
import {
  formatBattery,
  formatDate,
  formatLevel,
  formatRelative,
} from "./format";
import { localize, type Language } from "./i18n";
import { errorMessage } from "./settings-page";
import { icon, statusIcon, statusTone } from "./status";
import { sharedStyles } from "./styles";
import type { HomeAssistant } from "./types";

interface DeviceUpdate {
  mode: DeviceMode;
  overrides: Partial<Settings>;
  importance: Importance | null;
  battery_class: BatteryClass | null;
}

const CLASSES: BatteryClass[] = [
  "replaceable",
  "rechargeable",
  "robot",
  "vehicle",
  "ups",
  "home_battery",
  "unknown",
];
const IMPORTANCES: Importance[] = ["low", "normal", "important", "critical"];
const SNOOZE_DAYS = [1, 3, 7];

/**
 * The read-only sheet of one battery device, opened by `?device=<key>`.
 *
 * Live values come from the feed (`device`); the rest is fetched when the
 * sheet opens and again whenever the feed changes the device.
 */
export class BatteryCareDeviceSheet extends LitElement {
  static override properties = {
    hass: { attribute: false },
    deviceKey: { attribute: false },
    device: { attribute: false },
    ready: { attribute: false },
    language: { attribute: false },
    locale: { attribute: false },
    _details: { state: true },
    _failed: { state: true },
    _saveError: { state: true },
    _snoozeError: { state: true },
  };

  declare hass: HomeAssistant | undefined;
  declare deviceKey: string | null;
  declare device: DeviceView | undefined;
  declare ready: boolean;
  declare language: Language;
  declare locale: string;
  declare _details: DeviceDetails | undefined;
  declare _failed: boolean;
  declare _saveError: string | undefined;
  declare _snoozeError: string | undefined;

  private request = 0;

  constructor() {
    super();
    this.deviceKey = null;
    this.ready = false;
    this.language = "en";
    this.locale = "en";
    this._failed = false;
  }

  protected override willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("deviceKey")) {
      this._details = undefined;
      this._failed = false;
      this._saveError = undefined;
      this._snoozeError = undefined;
    }
    if (
      (changed.has("deviceKey") || changed.has("device")) &&
      this.deviceKey !== null &&
      this.device !== undefined
    ) {
      void this.load(this.deviceKey);
    }
  }

  protected override updated(): void {
    const dialog = this.renderRoot.querySelector("dialog");
    if (dialog === null) {
      return;
    }
    if (this.deviceKey !== null && !dialog.open) {
      dialog.showModal();
    } else if (this.deviceKey === null && dialog.open) {
      dialog.close();
    }
  }

  private async load(key: string): Promise<void> {
    const request = ++this.request;
    try {
      const details = await this.hass?.callWS<DeviceDetails>({
        type: "battery_care/device/get",
        key,
      });
      if (request === this.request) {
        this._details = details;
        this._failed = false;
      }
    } catch {
      if (request === this.request) {
        this._failed = true;
      }
    }
  }

  private readonly close = (): void => {
    this.renderRoot.querySelector("dialog")?.close();
  };

  private readonly handleClose = (): void => {
    // Also reached when the URL closed the sheet; only then is the key gone.
    if (this.deviceKey !== null) {
      this.dispatchEvent(new CustomEvent("sheet-closed"));
    }
  };

  private readonly handleClick = (event: MouseEvent): void => {
    // The content fills the dialog: a click on the dialog is on the backdrop.
    if (event.target === event.currentTarget) {
      this.close();
    }
  };

  protected override render(): TemplateResult {
    return html`<dialog
      aria-labelledby="title"
      @close=${this.handleClose}
      @click=${this.handleClick}
    >
      <div class="sheet">
        <div class="sheet-bar">
          <button
            class="icon-button"
            aria-label=${localize(this.language, "sheet.close")}
            @click=${this.close}
          >
            ${icon(mdiClose)}
          </button>
        </div>
        ${this.deviceKey === null ? nothing : this.renderBody()}
      </div>
    </dialog>`;
  }

  private renderBody(): TemplateResult {
    const { language } = this;
    const device = this.device;
    if (device === undefined) {
      return this.ready
        ? html`<p class="message" id="title">
            ${localize(language, "sheet.missing")}
          </p>`
        : html`<p class="message secondary" id="title">
            ${localize(language, "feed.loading")}
          </p>`;
    }
    const details = this._details;
    const subtitle = [device.area, details?.integration].filter(Boolean);
    const tone = statusTone(device);
    return html`
      <h2 id="title">${device.name}</h2>
      ${
        subtitle.length
          ? html`<p class="secondary subtitle">${subtitle.join(" · ")}</p>`
          : nothing
      }
      <div class="hero">
        ${
          device.level === null
            ? nothing
            : html`<span class="hero-level"
                >${formatLevel(device.level, this.locale)}</span
              >`
        }
        <span class="hero-status">
          <span class="tone-${tone}">${icon(statusIcon(device))}</span>
          ${localize(language, `status.${device.status}`)}
        </span>
      </div>
      <dl class="facts">
        ${this.fact(
          "sheet.battery",
          device.battery
            ? formatBattery(device.battery, this.locale)
            : localize(language, "sheet.battery_unknown"),
        )}
        ${details ? this.renderDetails(details) : nothing}
      </dl>
      ${
        this._failed
          ? html`<p class="message secondary">
              ${localize(language, "sheet.load_failed")}
            </p>`
          : nothing
      }
      ${details ? this.renderSnooze(details) : nothing}
      ${details && this.admin ? this.renderCustomize(details) : nothing}
      ${details ? this.renderSources(details) : nothing}
    `;
  }

  private async snooze(details: DeviceDetails, days: number): Promise<void> {
    this._snoozeError = undefined;
    try {
      const saved = await this.hass?.callWS<DeviceDetails>({
        type: "battery_care/device/snooze",
        key: details.device.key,
        days,
      });
      if (saved !== undefined) {
        this._details = saved;
      }
    } catch (error) {
      this._snoozeError = errorMessage(error, this.language);
    }
  }

  /** Notifications can wait a few days, for a battery that needs attention. */
  private renderSnooze(
    details: DeviceDetails,
  ): TemplateResult | typeof nothing {
    const { language } = this;
    const until = details.snoozed_until;
    if (until === null && !details.device.attention) {
      return nothing;
    }
    return html`<section class="snooze">
      <h3>${localize(language, "snooze.title")}</h3>
      ${
        until === null
          ? html`<div class="snooze-actions">
              ${SNOOZE_DAYS.map(
                (days) =>
                  html`<button
                    class="text-button"
                    @click=${() => void this.snooze(details, days)}
                  >
                    ${localize(language, "snooze.days", { count: days })}
                  </button>`,
              )}
            </div>`
          : html`<p class="secondary">
                ${localize(language, "snooze.until", {
                  date: formatDate(new Date(until), this.locale),
                })}
              </p>
              <button
                class="text-button"
                @click=${() => void this.snooze(details, 0)}
              >
                ${localize(language, "snooze.stop")}
              </button>`
      }
      ${
        this._snoozeError
          ? html`<p class="message error" role="alert">${this._snoozeError}</p>`
          : nothing
      }
    </section>`;
  }

  private get admin(): boolean {
    return this.hass?.user?.is_admin === true;
  }

  /** Save the user's choices for this device; the backend keeps what matters. */
  private async save(
    details: DeviceDetails,
    changes: Partial<DeviceUpdate>,
  ): Promise<void> {
    const update: DeviceUpdate = {
      mode: details.mode,
      overrides: details.overrides,
      importance: details.chosen_importance,
      battery_class: details.chosen_class,
      ...changes,
    };
    this._saveError = undefined;
    try {
      const saved = await this.hass?.callWS<DeviceDetails>({
        type: "battery_care/device/update",
        key: details.device.key,
        ...update,
        overrides: update.mode === "custom" ? update.overrides : {},
      });
      if (saved !== undefined) {
        this._details = saved;
        this.dispatchEvent(
          new CustomEvent("device-saved", {
            detail: { key: saved.device.key },
          }),
        );
      }
    } catch (error) {
      this._saveError = errorMessage(error, this.language, details.limits);
    }
  }

  private renderCustomize(details: DeviceDetails): TemplateResult {
    const { language } = this;
    const ignored = details.mode === "ignored";
    const custom = details.mode === "custom";
    const threshold = (key: "low_threshold" | "critical_threshold") =>
      html`<label class="field">
        <span>${localize(language, `customize.${key}`)}</span>
        <span class="input">
          <input
            type="number"
            inputmode="numeric"
            step="1"
            min=${details.limits[key]?.[0] ?? nothing}
            max=${details.limits[key]?.[1] ?? nothing}
            .value=${live(String(details.overrides[key] ?? details.inherited[key] ?? ""))}
            @change=${(event: Event) => {
              const value = Number((event.target as HTMLInputElement).value);
              if (Number.isInteger(value)) {
                void this.save(details, {
                  overrides: { ...details.overrides, [key]: value },
                });
              }
            }}
          />
          <span class="unit secondary">%</span>
        </span>
      </label>`;
    return html`<section class="customize">
      <h3>${localize(language, "customize.title")}</h3>
      ${
        ignored
          ? html`<p class="secondary">
              ${localize(language, "customize.ignored_help")}
            </p>`
          : html`
              <label class="field">
                <span>${localize(language, "customize.type")}</span>
                <select
                  .value=${live(details.chosen_class ?? "")}
                  @change=${(event: Event) => {
                    const value = (event.target as HTMLSelectElement).value;
                    void this.save(details, {
                      battery_class:
                        value === "" ? null : (value as BatteryClass),
                    });
                  }}
                >
                  <option value="" ?selected=${details.chosen_class === null}>
                    ${localize(language, "customize.automatic", {
                      value: localize(
                        language,
                        `class.${details.detected_class}`,
                      ),
                    })}
                  </option>
                  ${CLASSES.map(
                    (value) =>
                      html`<option
                        value=${value}
                        ?selected=${details.chosen_class === value}
                      >
                        ${localize(language, `class.${value}`)}
                      </option>`,
                  )}
                </select>
              </label>
              <label class="field">
                <span>${localize(language, "sheet.importance")}</span>
                <select
                  .value=${live(details.chosen_importance ?? "")}
                  @change=${(event: Event) => {
                    const value = (event.target as HTMLSelectElement).value;
                    void this.save(details, {
                      importance: value === "" ? null : (value as Importance),
                    });
                  }}
                >
                  <option
                    value=""
                    ?selected=${details.chosen_importance === null}
                  >
                    ${localize(language, "customize.automatic", {
                      value: localize(
                        language,
                        `importance.${details.suggested_importance}`,
                      ),
                    })}
                  </option>
                  ${IMPORTANCES.map(
                    (value) =>
                      html`<option
                        value=${value}
                        ?selected=${details.chosen_importance === value}
                      >
                        ${localize(language, `importance.${value}`)}
                      </option>`,
                  )}
                </select>
              </label>
              <label class="field">
                <span>${localize(language, "customize.own_thresholds")}</span>
                <input
                  type="checkbox"
                  role="switch"
                  .checked=${live(custom)}
                  @change=${(event: Event) => {
                    const checked = (event.target as HTMLInputElement).checked;
                    void this.save(details, {
                      mode: checked ? "custom" : "automatic",
                      overrides: {},
                    });
                  }}
                />
              </label>
              ${custom ? threshold("low_threshold") : nothing}
              ${custom ? threshold("critical_threshold") : nothing}
            `
      }
      ${
        this._saveError
          ? html`<p class="message error" role="alert">${this._saveError}</p>`
          : nothing
      }
      <button
        class="text-button"
        @click=${() =>
          void this.save(details, {
            mode: ignored ? "automatic" : "ignored",
            overrides: {},
          })}
      >
        ${localize(language, ignored ? "customize.stop_ignoring" : "customize.ignore")}
      </button>
    </section>`;
  }

  private fact(label: string, value: string): TemplateResult {
    return html`<div class="fact">
      <dt class="secondary">${localize(this.language, label)}</dt>
      <dd>${value}</dd>
    </div>`;
  }

  private renderDetails(details: DeviceDetails): TemplateResult {
    const { language, locale } = this;
    const { device } = details;
    const lastReport = details.last_report
      ? formatRelative(new Date(details.last_report), locale)
      : localize(language, "sheet.never");
    const category = `${localize(language, `class.${device.battery_class}`)} · ${localize(language, `class_reason.${details.class_reason}`)}`;
    let importance = localize(language, `importance.${device.importance}`);
    if (details.importance_source !== "default") {
      importance += ` (${localize(language, `importance_source.${details.importance_source}`)})`;
    }
    let alerts: string;
    if (details.mode === "ignored") {
      alerts = localize(language, "alerts.ignored");
    } else if (!details.alerts) {
      alerts = localize(language, "alerts.off");
    } else {
      alerts = localize(language, `alerts.${details.mode}`, {
        low: formatLevel(details.low_threshold, locale),
        critical: formatLevel(details.critical_threshold, locale),
      });
    }
    return html`
      ${this.fact("sheet.last_report", lastReport)}
      ${this.fact("sheet.category", category)}
      ${this.fact("sheet.importance", importance)}
      ${this.fact("sheet.alerts", alerts)}
    `;
  }

  private sourceState(source: Source): string {
    const { language } = this;
    const { state } = source;
    if (state === null || state === "unknown") {
      return localize(language, "source.unknown");
    }
    if (state === "unavailable") {
      return localize(language, "source.unavailable");
    }
    if (source.kind === "level") {
      const level = Number(state);
      return Number.isFinite(level) ? formatLevel(level, this.locale) : state;
    }
    if (state === "on" || state === "off") {
      return localize(language, `source.${source.kind}_${state}`);
    }
    return state;
  }

  private renderSources(details: DeviceDetails): TemplateResult {
    const { language } = this;
    return html`
      ${
        details.stable
          ? nothing
          : html`<p class="message secondary">
              ${localize(language, "sheet.unstable")}
            </p>`
      }
      <details class="sources">
        <summary>
          <span>${localize(language, "sheet.entities")}</span>
          ${icon(mdiChevronDown)}
        </summary>
        <ul>
          ${details.sources.map(
            (source) =>
              html`<li>
                <span>${source.name}</span>
                <span class="secondary"
                  >${localize(language, `source.${source.kind}`)} ·
                  ${this.sourceState(source)}</span
                >
                <code class="secondary"
                  >${
                    source.attribute
                      ? `${source.entity_id} · ${source.attribute}`
                      : source.entity_id
                  }</code
                >
              </li>`,
          )}
        </ul>
      </details>
    `;
  }

  static override styles = [
    sharedStyles,
    css`
      dialog {
        box-sizing: border-box;
        width: 100%;
        max-width: 100%;
        height: 100%;
        max-height: 100%;
        margin: 0;
        padding: 0;
        border: none;
        background: var(--bc-card);
        color: var(--bc-text);
        overscroll-behavior: contain;
      }
      dialog::backdrop {
        background: rgba(0, 0, 0, 0.32);
      }
      @media (min-width: 870px) {
        dialog {
          width: 420px;
          margin-inline-start: auto;
          border-inline-start: 1px solid var(--bc-divider);
        }
      }
      dialog[open] {
        animation: slide-in 180ms ease-out;
      }
      @keyframes slide-in {
        from {
          transform: translateY(24px);
          opacity: 0;
        }
      }
      @media (min-width: 870px) {
        @keyframes slide-in {
          from {
            transform: translateX(24px);
            opacity: 0;
          }
        }
      }
      .sheet {
        min-height: 100%;
        padding: 4px 24px 32px;
        padding-top: max(4px, var(--safe-area-inset-top, 0px));
        padding-bottom: max(32px, var(--safe-area-inset-bottom, 0px));
        box-sizing: border-box;
      }
      .sheet-bar {
        display: flex;
        justify-content: flex-end;
        margin-inline-end: -12px;
      }
      h2 {
        margin: 0;
        font-size: 22px;
        font-weight: 500;
        overflow-wrap: anywhere;
      }
      .subtitle {
        margin: 4px 0 0;
      }
      .hero {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 8px 16px;
        margin: 20px 0 8px;
      }
      .hero-level {
        font-size: 44px;
        font-weight: 400;
        line-height: 1;
        font-variant-numeric: tabular-nums;
      }
      .hero-status {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        font-weight: 500;
      }
      .hero-status > span {
        display: inline-flex;
      }
      .facts {
        margin: 16px 0;
        border-top: 1px solid var(--bc-divider);
      }
      .fact {
        display: grid;
        grid-template-columns: minmax(96px, 35%) 1fr;
        gap: 12px;
        padding: 12px 0;
        border-bottom: 1px solid var(--bc-divider);
      }
      dt,
      dd {
        margin: 0;
      }
      .message {
        margin: 16px 0;
      }
      .customize,
      .snooze {
        display: flex;
        flex-direction: column;
        align-items: stretch;
        margin: 16px 0;
        padding: 8px 0;
        border-top: 1px solid var(--bc-divider);
        border-bottom: 1px solid var(--bc-divider);
      }
      .snooze {
        align-items: flex-start;
      }
      .snooze + .customize {
        margin-top: 0;
        border-top: 0;
      }
      .snooze p {
        margin: 0 0 8px;
      }
      .snooze-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
      .customize h3,
      .snooze h3 {
        margin: 8px 0;
        font-size: 16px;
        font-weight: 500;
      }
      .customize .field {
        padding: 0;
      }
      .customize p {
        margin: 0 0 8px;
      }
      .customize .text-button {
        align-self: flex-start;
        margin-left: -12px;
      }
      .sources summary {
        min-height: 48px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        cursor: pointer;
        font-weight: 500;
        list-style: none;
      }
      .sources summary::-webkit-details-marker {
        display: none;
      }
      .sources summary .icon {
        transition: transform 0.2s;
      }
      .sources[open] summary .icon {
        transform: rotate(180deg);
      }
      .sources ul {
        margin: 0;
        padding: 0;
        list-style: none;
      }
      .sources li {
        display: flex;
        flex-direction: column;
        gap: 2px;
        padding: 8px 0;
        border-bottom: 1px solid var(--bc-divider);
        overflow-wrap: anywhere;
      }
      code {
        font-size: 12px;
      }
    `,
  ];
}

if (!customElements.get("battery-care-device-sheet")) {
  customElements.define("battery-care-device-sheet", BatteryCareDeviceSheet);
}

declare global {
  interface HTMLElementTagNameMap {
    "battery-care-device-sheet": BatteryCareDeviceSheet;
  }
}
