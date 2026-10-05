import { mdiMenu } from "@mdi/js";
import {
  LitElement,
  css,
  html,
  nothing,
  type PropertyValues,
  type TemplateResult,
} from "lit";
import {
  Feed,
  type DeviceView,
  type FeedStatus,
  type Patch,
  type Snapshot,
  type Summary,
} from "./api";
import "./device-sheet";
import { intlLocale } from "./format";
import { localize, resolveLanguage, type Language } from "./i18n";
import {
  devicePath,
  followLink,
  leaveTo,
  parseLocation,
  viewPath,
  type View,
} from "./router";
import "./settings-page";
import { icon } from "./status";
import { sharedStyles } from "./styles";
import type { Connection, HomeAssistant, Route } from "./types";
import { renderAll, renderOverview, renderSkeleton } from "./views";

const DEFAULT_PREFIX = "/battery-care";

/** Whether a new `hass` object changes anything this panel shows. */
function hassChanged(
  old: HomeAssistant | undefined,
  hass: HomeAssistant | undefined,
): boolean {
  return (
    old?.connection !== hass?.connection ||
    old?.language !== hass?.language ||
    old?.locale?.language !== hass?.locale?.language ||
    old?.dockedSidebar !== hass?.dockedSidebar ||
    old?.kioskMode !== hass?.kioskMode
  );
}

export class BatteryCarePanel extends LitElement {
  static override properties = {
    hass: { attribute: false },
    narrow: { type: Boolean, reflect: true },
    route: { attribute: false },
    _devices: { state: true },
    _summary: { state: true },
    _ready: { state: true },
    _status: { state: true },
    _search: { state: true },
    _revision: { state: true },
  };

  declare hass: HomeAssistant | undefined;
  declare narrow: boolean;
  declare route: Route | undefined;
  declare _devices: ReadonlyMap<string, DeviceView>;
  declare _summary: Summary | undefined;
  declare _ready: boolean;
  declare _status: FeedStatus;
  declare _search: string;
  declare _revision: number;

  private feed: Feed | undefined;
  private feedConnection: Connection | undefined;

  constructor() {
    super();
    this.narrow = false;
    this._devices = new Map();
    this._ready = false;
    this._status = "connecting";
    this._search = window.location.search;
    this._revision = 0;
  }

  override connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("location-changed", this.handleLocation);
    window.addEventListener("popstate", this.handleLocation);
    this.handleLocation();
    this.syncFeed();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    window.removeEventListener("location-changed", this.handleLocation);
    window.removeEventListener("popstate", this.handleLocation);
    this.stopFeed();
  }

  protected override shouldUpdate(changed: PropertyValues<this>): boolean {
    // Home Assistant sets a new hass object on every state change.
    if (changed.size === 1 && changed.has("hass")) {
      return hassChanged(changed.get("hass"), this.hass);
    }
    return true;
  }

  protected override willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("hass")) {
      this.syncFeed();
    }
  }

  private syncFeed(): void {
    const connection = this.hass?.connection;
    if (!this.isConnected || connection === this.feedConnection) {
      return;
    }
    this.stopFeed();
    if (connection === undefined) {
      return;
    }
    this.feedConnection = connection;
    this.feed = new Feed(connection, this.handleMessage, this.handleStatus);
    this.feed.start();
  }

  private stopFeed(): void {
    this.feed?.stop();
    this.feed = undefined;
    this.feedConnection = undefined;
  }

  private readonly handleMessage = (message: Snapshot | Patch): void => {
    const devices =
      message.type === "snapshot" ? new Map() : new Map(this._devices);
    for (const device of message.devices) {
      devices.set(device.key, device);
    }
    this._devices = devices;
    this._summary = message.summary;
    if (message.type === "snapshot") {
      this._ready = message.ready;
    }
  };

  private readonly handleStatus = (status: FeedStatus): void => {
    this._status = status;
  };

  private readonly handleLocation = (): void => {
    this._search = window.location.search;
  };

  private get basePath(): string {
    return this.route?.prefix ?? DEFAULT_PREFIX;
  }

  private get view(): View {
    return parseLocation(this.route?.path ?? "", "").view;
  }

  private readonly handleClick = (event: MouseEvent): void => {
    const link = (event.target as Element | null)?.closest("a[href]");
    const path = link?.getAttribute("href");
    if (path) {
      followLink(event, path);
    }
  };

  private readonly toggleMenu = (): void => {
    this.dispatchEvent(
      new CustomEvent("hass-toggle-menu", {
        bubbles: true,
        composed: true,
        detail: {},
      }),
    );
  };

  private readonly closeDevice = (): void => {
    leaveTo(viewPath(this.basePath, this.view));
  };

  /** Shown when and where Home Assistant shows its own menu button. */
  private get showMenuButton(): boolean {
    const { hass } = this;
    return (
      hass?.kioskMode !== true &&
      hass?.auth?.external?.config?.hasSidebar !== true &&
      (this.narrow || hass?.dockedSidebar === "always_hidden")
    );
  }

  protected override render(): TemplateResult {
    const language = resolveLanguage(
      this.hass?.locale?.language ?? this.hass?.language,
    );
    const locale = intlLocale(
      this.hass?.locale?.language ?? this.hass?.language,
    );
    const { basePath, view } = this;
    const device = parseLocation("", this._search).device;
    return html`
      <div class="layout" @click=${this.handleClick}>
        <header class="toolbar">
          ${
            this.showMenuButton
              ? html`<button
                  class="icon-button"
                  aria-label=${localize(language, "panel.menu")}
                  @click=${this.toggleMenu}
                >
                  ${icon(mdiMenu)}
                </button>`
              : nothing
          }
          <h1>${localize(language, "panel.title")}</h1>
        </header>
        <nav class="tabs" aria-label=${localize(language, "panel.views")}>
          ${(["overview", "all", "settings"] as const).map(
            (tab) =>
              html`<a
                class="tab"
                href=${viewPath(basePath, tab)}
                aria-current=${tab === view ? "page" : nothing}
                >${localize(language, `nav.${tab}`)}</a
              >`,
          )}
        </nav>
        <main>
          ${this.renderBanner(language)}
          ${this.renderContent(language, locale, view)}
        </main>
      </div>
      <battery-care-device-sheet
        .hass=${this.hass}
        .deviceKey=${device}
        .device=${device === null ? undefined : this._devices.get(device)}
        .ready=${this._ready}
        .language=${language}
        .locale=${locale}
        @sheet-closed=${this.closeDevice}
        @device-saved=${() => {
          this._revision += 1;
        }}
      ></battery-care-device-sheet>
    `;
  }

  private renderBanner(language: Language): TemplateResult | typeof nothing {
    if (this._status === "outdated") {
      return html`<div class="banner" role="alert">
        <span>${localize(language, "feed.outdated")}</span>
        <button
          class="text-button"
          @click=${() => {
            window.location.reload();
          }}
        >
          ${localize(language, "feed.reload")}
        </button>
      </div>`;
    }
    if (this._status === "unavailable") {
      return html`<div class="banner" role="status">
        ${localize(language, "feed.unavailable")}
      </div>`;
    }
    return nothing;
  }

  private renderContent(
    language: Language,
    locale: string,
    view: View,
  ): TemplateResult | typeof nothing {
    if (view === "settings") {
      return html`<battery-care-settings
        .hass=${this.hass}
        .language=${language}
        .revision=${this._revision}
        .deviceHref=${(key: string) => devicePath(this.basePath, view, key)}
      ></battery-care-settings>`;
    }
    const summary = this._summary;
    if (summary === undefined || !this._ready) {
      if (this._status === "outdated" || this._status === "unavailable") {
        return nothing;
      }
      return renderSkeleton(
        localize(language, summary ? "feed.waiting" : "feed.loading"),
      );
    }
    const context = {
      language,
      locale,
      deviceHref: (key: string) => devicePath(this.basePath, view, key),
    };
    const devices = this._devices.values();
    return view === "all"
      ? renderAll(devices, context)
      : renderOverview(
          devices,
          summary,
          viewPath(this.basePath, "all"),
          context,
        );
  }

  static override styles = [
    sharedStyles,
    css`
      :host {
        display: block;
        min-height: 100%;
        background: var(--primary-background-color);
        -webkit-tap-highlight-color: transparent;
      }
      .toolbar {
        display: flex;
        align-items: center;
        gap: 4px;
        box-sizing: border-box;
        min-height: var(--header-height, 56px);
        padding: 0 12px;
        background: var(--app-header-background-color, var(--primary-color));
        color: var(--app-header-text-color, var(--text-primary-color, #fff));
        border-bottom: var(--app-header-border-bottom, none);
      }
      h1 {
        margin: 0;
        padding-inline-start: 4px;
        font-size: 20px;
        font-weight: 400;
      }
      .tabs {
        display: flex;
        gap: 8px;
        padding: 0 16px;
        background: var(--app-header-background-color, var(--primary-color));
        color: var(--app-header-text-color, var(--text-primary-color, #fff));
      }
      .tab {
        display: inline-flex;
        align-items: center;
        min-height: 48px;
        padding: 0 12px;
        color: inherit;
        text-decoration: none;
        opacity: 0.8;
        border-bottom: 2px solid transparent;
      }
      .tab[aria-current="page"] {
        opacity: 1;
        font-weight: 500;
        border-bottom-color: currentColor;
      }
      main {
        box-sizing: border-box;
        max-width: 960px;
        margin: 0 auto;
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 16px;
      }
      .banner {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 8px 16px;
        padding: 12px 16px;
        border-radius: var(--bc-radius);
        border: 1px solid var(--bc-border);
        background: var(--bc-card);
      }
      .text-button {
        min-height: 40px;
        padding: 0 16px;
        border: 1px solid var(--bc-accent);
        border-radius: 20px;
        background: none;
        color: var(--bc-accent);
        font: inherit;
        font-weight: 500;
        cursor: pointer;
      }
      .summary h2 {
        margin: 0;
        padding: 16px 16px 12px;
        font-size: 20px;
        font-weight: 400;
      }
      .counts {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 1px;
        margin: 0;
        border-top: 1px solid var(--bc-divider);
        background: var(--bc-divider);
      }
      /* An odd count out spans the row instead of leaving a gap. */
      .count:last-child:nth-child(odd) {
        grid-column: 1 / -1;
      }
      @container (min-width: 600px) {
        .counts {
          grid-template-columns: none;
          grid-auto-columns: minmax(0, 1fr);
          grid-auto-flow: column;
        }
        .count:last-child:nth-child(odd) {
          grid-column: auto;
        }
      }
      .count {
        display: flex;
        flex-direction: column-reverse;
        gap: 2px;
        padding: 12px 16px;
        background: var(--bc-card);
      }
      .count dt {
        display: flex;
        align-items: center;
        gap: 6px;
        color: var(--bc-secondary);
      }
      .count dd {
        margin: 0;
        font-size: 24px;
        font-variant-numeric: tabular-nums;
      }
      .dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: currentColor;
      }
      .rows {
        margin: 0;
        padding: 4px 0;
        list-style: none;
      }
      .row {
        display: flex;
        align-items: center;
        gap: 16px;
        min-height: 64px;
        padding: 8px 16px;
        box-sizing: border-box;
        color: inherit;
        text-decoration: none;
      }
      a.row:hover {
        background: var(--bc-hover);
      }
      .row-icon {
        display: inline-flex;
      }
      .row-text {
        display: flex;
        flex: 1;
        min-width: 0;
        flex-direction: column;
        gap: 2px;
      }
      .row-name {
        display: -webkit-box;
        -webkit-box-orient: vertical;
        -webkit-line-clamp: 2;
        overflow: hidden;
        overflow-wrap: break-word;
      }
      .row-details {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-size: 14px;
      }
      .row-value {
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        gap: 2px;
        max-width: 40%;
        text-align: end;
      }
      .row-level {
        font-variant-numeric: tabular-nums;
      }
      .row-status {
        font-size: 14px;
        color: var(--bc-secondary);
      }
      .row-status.strong {
        color: var(--bc-text);
        font-weight: 500;
      }
      .see-all {
        align-self: center;
        display: inline-flex;
        align-items: center;
        min-height: 48px;
        padding: 0 16px;
        color: var(--bc-accent);
        font-weight: 500;
        text-decoration: none;
      }
      .empty {
        padding-bottom: 8px;
      }
      .empty p {
        margin: 0;
        padding: 4px 16px 12px;
      }
      .skeleton-icon {
        width: 24px;
        height: 24px;
        border-radius: 50%;
      }
      .skeleton-line {
        width: 60%;
        height: 14px;
      }
      .skeleton-line.short {
        width: 35%;
        margin-top: 6px;
      }
      .layout {
        container-type: inline-size;
      }
    `,
  ];
}

if (!customElements.get("battery-care-panel")) {
  customElements.define("battery-care-panel", BatteryCarePanel);
}

declare global {
  interface HTMLElementTagNameMap {
    "battery-care-panel": BatteryCarePanel;
  }
}
