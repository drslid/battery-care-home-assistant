import { LitElement, css, html, nothing, type TemplateResult } from "lit";
import { live } from "lit/directives/live.js";
import type {
  ClassRow,
  DeviceDetails,
  Limits,
  Settings,
  SettingsView,
} from "./api";
import { localize, type Language } from "./i18n";
import { sharedStyles } from "./styles";
import type { HomeAssistant } from "./types";

type Changes = Partial<Settings>;

const KNOWN_ERRORS = new Set([
  "out_of_range",
  "critical_not_below_low",
  "recovery_above_maximum",
]);

/** Turn a refused change ("key: code") into a sentence for the user. */
export function errorMessage(
  error: unknown,
  language: Language,
  limits: Limits = {},
): string {
  const message =
    typeof error === "object" && error !== null && "message" in error
      ? String(error.message)
      : "";
  const [key = "", code = ""] = message.split(": ");
  const limit = limits[key as keyof Settings];
  if (code === "out_of_range" && limit) {
    return localize(language, "settings.error.between", {
      min: limit[0],
      max: limit[1],
    });
  }
  return localize(
    language,
    `settings.error.${KNOWN_ERRORS.has(code) ? code : "other"}`,
  );
}

/**
 * The Settings page: alerts per battery type, reminders and delays, and the
 * ignored batteries. Every change is saved at once; non-admins only read.
 */
export class BatteryCareSettings extends LitElement {
  static override properties = {
    hass: { attribute: false },
    language: { attribute: false },
    deviceHref: { attribute: false },
    revision: { attribute: false },
    _view: { state: true },
    _failed: { state: true },
    _error: { state: true },
  };

  declare hass: HomeAssistant | undefined;
  declare language: Language;
  declare deviceHref: (key: string) => string;
  /** Changes when a battery's choices were saved elsewhere. */
  declare revision: number;
  declare _view: SettingsView | undefined;
  declare _failed: boolean;
  declare _error: string | undefined;

  constructor() {
    super();
    this.language = "en";
    this.deviceHref = (key) => `?device=${encodeURIComponent(key)}`;
    this.revision = 0;
    this._failed = false;
  }

  override connectedCallback(): void {
    super.connectedCallback();
    void this.load();
  }

  protected override updated(changed: Map<PropertyKey, unknown>): void {
    if (changed.has("revision") && changed.get("revision") !== undefined) {
      void this.load();
    }
  }

  private get admin(): boolean {
    return this.hass?.user?.is_admin === true;
  }

  private async load(): Promise<void> {
    try {
      this._view = await this.hass?.callWS<SettingsView>({
        type: "battery_care/settings/get",
      });
      this._failed = false;
    } catch {
      this._failed = true;
    }
  }

  private async send(message: {
    type: string;
    [key: string]: unknown;
  }): Promise<void> {
    this._error = undefined;
    try {
      const view = await this.hass?.callWS<SettingsView>(message);
      if (view !== undefined) {
        this._view = view;
      }
    } catch (error) {
      this._error = errorMessage(error, this.language, this._view?.limits);
      // Show the stored values again instead of the refused ones.
      await this.load();
    }
  }

  private updateSettings(changes: Changes): void {
    void this.send({ type: "battery_care/settings/update", changes });
  }

  private updateClass(row: ClassRow, changes: Changes): void {
    void this.send({
      type: "battery_care/class/update",
      battery_class: row.battery_class,
      changes,
    });
  }

  private async stopIgnoring(key: string): Promise<void> {
    this._error = undefined;
    try {
      // An update replaces every choice: keep the device's type and importance.
      const details = await this.hass?.callWS<DeviceDetails>({
        type: "battery_care/device/get",
        key,
      });
      await this.hass?.callWS({
        type: "battery_care/device/update",
        key,
        mode: "automatic",
        importance: details?.chosen_importance ?? null,
        battery_class: details?.chosen_class ?? null,
      });
    } catch (error) {
      this._error = errorMessage(error, this.language);
    }
    await this.load();
  }

  protected override render(): TemplateResult {
    const { language } = this;
    const view = this._view;
    if (view === undefined) {
      return html`<p class="message ${this._failed ? "" : "secondary"}">
        ${localize(language, this._failed ? "settings.load_failed" : "settings.loading")}
      </p>`;
    }
    return html`
      ${
        this.admin
          ? nothing
          : html`<p class="message secondary">
              ${localize(language, "settings.read_only")}
            </p>`
      }
      ${
        this._error
          ? html`<p class="message error" role="alert">${this._error}</p>`
          : nothing
      }
      ${this.renderClasses(view)} ${this.renderGeneral(view)}
      ${this.renderIgnored(view)}
    `;
  }

  private renderClasses(view: SettingsView): TemplateResult {
    const { language } = this;
    return html`<section class="card">
      <h2>${localize(language, "settings.classes_title")}</h2>
      <p class="help secondary">
        ${localize(language, "settings.classes_help")}
      </p>
      <ul class="classes">
        ${view.classes.map(
          (row) =>
            html`<li class="class-row">
              <div class="class-name">
                <span>${localize(language, `class.${row.battery_class}`)}</span>
                <span class="secondary">
                  ${localize(language, "settings.devices", { count: row.devices })}
                </span>
              </div>
              ${this.toggle(
                localize(language, "settings.alerts"),
                row.alerts_enabled,
                (checked) => {
                  this.updateClass(row, { alerts_enabled: checked });
                },
              )}
              ${this.number(
                localize(language, "settings.low"),
                row.low_threshold,
                view.limits.low_threshold,
                (value) => {
                  this.updateClass(row, { low_threshold: value });
                },
                "%",
              )}
              ${this.number(
                localize(language, "settings.critical"),
                row.critical_threshold,
                view.limits.critical_threshold,
                (value) => {
                  this.updateClass(row, { critical_threshold: value });
                },
                "%",
              )}
            </li>`,
        )}
      </ul>
    </section>`;
  }

  private renderGeneral(view: SettingsView): TemplateResult {
    const { language } = this;
    const { settings, limits } = view;
    const field = (key: keyof Settings, unit?: string) =>
      this.number(
        localize(language, `settings.${key}`),
        settings[key] as number,
        limits[key],
        (value) => {
          this.updateSettings({ [key]: value });
        },
        unit,
      );
    const toggle = (key: keyof Settings) =>
      this.toggle(
        localize(language, `settings.${key}`),
        settings[key] as boolean,
        (checked) => {
          this.updateSettings({ [key]: checked });
        },
      );
    return html`<section class="card">
        <h2>${localize(language, "settings.general_title")}</h2>
        <div class="fields">
          ${toggle("alerts_enabled")} ${field("reminder_hours", "h")}
          ${toggle("unavailable_alerts")}
          ${field("unavailable_grace_hours", "h")} ${toggle("stale_detection")}
          ${field("stale_days", localize(language, "settings.days"))}
        </div>
      </section>
      <section class="card">
        <h2>${localize(language, "settings.advanced_title")}</h2>
        <div class="fields">
          ${field("hysteresis", "%")} ${field("binary_recovery_minutes", "min")}
        </div>
      </section>`;
  }

  private renderIgnored(view: SettingsView): TemplateResult {
    const { language } = this;
    return html`<section class="card">
      <h2>${localize(language, "settings.ignored_title")}</h2>
      ${
        view.ignored.length
          ? html`<ul class="ignored">
              ${view.ignored.map(
                (item) =>
                  html`<li>
                    <a href=${this.deviceHref(item.key)}>${item.name}</a>
                    ${
                      this.admin
                        ? html`<button
                            class="text-button"
                            @click=${() => void this.stopIgnoring(item.key)}
                          >
                            ${localize(language, "settings.stop_ignoring")}
                          </button>`
                        : nothing
                    }
                  </li>`,
              )}
            </ul>`
          : html`<p class="help secondary">
              ${localize(language, "settings.ignored_empty")}
            </p>`
      }
    </section>`;
  }

  private toggle(
    label: string,
    checked: boolean,
    changed: (checked: boolean) => void,
  ): TemplateResult {
    return html`<label class="field toggle">
      <span>${label}</span>
      <input
        type="checkbox"
        role="switch"
        .checked=${live(checked)}
        ?disabled=${!this.admin}
        @change=${(event: Event) => {
          changed((event.target as HTMLInputElement).checked);
        }}
      />
    </label>`;
  }

  private number(
    label: string,
    value: number,
    limit: [number, number] | undefined,
    changed: (value: number) => void,
    unit?: string,
  ): TemplateResult {
    return html`<label class="field">
      <span>${label}</span>
      <span class="input">
        <input
          type="number"
          inputmode="numeric"
          step="1"
          min=${limit?.[0] ?? nothing}
          max=${limit?.[1] ?? nothing}
          .value=${live(String(value))}
          ?disabled=${!this.admin}
          @change=${(event: Event) => {
            const input = event.target as HTMLInputElement;
            const parsed = Number(input.value);
            if (input.value === "" || !Number.isInteger(parsed)) {
              input.value = String(value);
              return;
            }
            changed(parsed);
          }}
        />
        ${unit ? html`<span class="unit secondary">${unit}</span>` : nothing}
      </span>
    </label>`;
  }

  static override styles = [
    sharedStyles,
    css`
      :host {
        display: flex;
        flex-direction: column;
        gap: 16px;
      }
      .help {
        margin: 0;
        padding: 0 16px 8px;
      }
      .message {
        margin: 0;
      }
      .classes,
      .ignored {
        margin: 0;
        padding: 0;
        list-style: none;
      }
      .class-row {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 8px 16px;
        padding: 12px 16px;
        border-top: 1px solid var(--bc-divider);
      }
      .class-name {
        display: flex;
        flex-direction: column;
        grid-column: 1 / -1;
      }
      .fields {
        display: flex;
        flex-direction: column;
        padding: 0 0 8px;
      }
      .class-row .field {
        padding: 0;
      }
      .ignored li {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        min-height: 48px;
        padding: 0 16px;
        border-top: 1px solid var(--bc-divider);
      }
      .ignored a {
        color: inherit;
      }
      @container (min-width: 600px) {
        .class-row {
          grid-template-columns: minmax(0, 1fr) repeat(3, auto);
          align-items: center;
        }
        .class-name {
          grid-column: auto;
        }
      }
    `,
  ];
}

if (!customElements.get("battery-care-settings")) {
  customElements.define("battery-care-settings", BatteryCareSettings);
}

declare global {
  interface HTMLElementTagNameMap {
    "battery-care-settings": BatteryCareSettings;
  }
}
