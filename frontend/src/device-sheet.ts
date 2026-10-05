import { mdiChevronDown, mdiClose } from "@mdi/js";
import {
  LitElement,
  css,
  html,
  nothing,
  type PropertyValues,
  type TemplateResult,
} from "lit";
import type { DeviceDetails, DeviceView, Source } from "./api";
import { formatBattery, formatLevel, formatRelative } from "./format";
import { localize, type Language } from "./i18n";
import { icon, statusIcon, statusTone } from "./status";
import { sharedStyles } from "./styles";
import type { HomeAssistant } from "./types";

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
  };

  declare hass: HomeAssistant | undefined;
  declare deviceKey: string | null;
  declare device: DeviceView | undefined;
  declare ready: boolean;
  declare language: Language;
  declare locale: string;
  declare _details: DeviceDetails | undefined;
  declare _failed: boolean;

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
      ${details ? this.renderSources(details) : nothing}
    `;
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
