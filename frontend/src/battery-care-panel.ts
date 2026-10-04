import { LitElement, css, html } from "lit";
import { localize, resolveLanguage } from "./i18n";
import type { HomeAssistant } from "./types";

export class BatteryCarePanel extends LitElement {
  static override properties = {
    hass: { attribute: false },
    narrow: { type: Boolean, reflect: true },
  };

  declare hass: HomeAssistant | undefined;
  declare narrow: boolean;

  constructor() {
    super();
    this.narrow = false;
  }

  protected override render() {
    const language = resolveLanguage(
      this.hass?.locale?.language ?? this.hass?.language,
    );
    return html`
      <header>
        <h1>${localize(language, "panel.title")}</h1>
      </header>
      <main>
        <p role="status">${localize(language, "panel.starting")}</p>
      </main>
    `;
  }

  static override styles = css`
    :host {
      display: block;
      min-height: 100%;
      background: var(--primary-background-color);
      color: var(--primary-text-color);
    }
    header {
      display: flex;
      align-items: center;
      min-height: var(--header-height, 56px);
      padding: 0 16px;
      background: var(--app-header-background-color, var(--primary-color));
      color: var(--app-header-text-color, var(--text-primary-color));
    }
    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 400;
    }
    main {
      padding: 16px;
    }
  `;
}

if (!customElements.get("battery-care-panel")) {
  customElements.define("battery-care-panel", BatteryCarePanel);
}
