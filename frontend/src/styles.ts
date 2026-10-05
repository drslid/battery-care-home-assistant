import { css } from "lit";

/**
 * Tokens from the Home Assistant theme, plus pieces the panel and the sheet
 * share. Colour marks icons and indicators only, so text keeps its contrast.
 */
export const sharedStyles = css`
  :host {
    --bc-radius: var(--ha-card-border-radius, 12px);
    --bc-card: var(--card-background-color, var(--ha-card-background, #fff));
    --bc-border: var(--ha-card-border-color, var(--divider-color, #e0e0e0));
    --bc-divider: var(--divider-color, #e0e0e0);
    --bc-text: var(--primary-text-color, #212121);
    --bc-secondary: var(--secondary-text-color, #727272);
    --bc-muted: var(--disabled-text-color, #bdbdbd);
    --bc-error: var(--error-color, #db4437);
    --bc-warning: var(--warning-color, #ffa600);
    --bc-accent: var(--primary-color, #03a9f4);
    --bc-hover: color-mix(in srgb, currentColor 8%, transparent);
    color: var(--bc-text);
  }
  .icon {
    width: 24px;
    height: 24px;
    flex: none;
    fill: currentColor;
  }
  .tone-error {
    color: var(--bc-error);
  }
  .tone-warning {
    color: var(--bc-warning);
  }
  .tone-muted {
    color: var(--bc-muted);
  }
  .secondary {
    color: var(--bc-secondary);
  }
  .icon-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 48px;
    height: 48px;
    padding: 0;
    border: none;
    border-radius: 50%;
    background: none;
    color: inherit;
    cursor: pointer;
  }
  .icon-button:hover {
    background: var(--bc-hover);
  }
  :focus-visible {
    outline: 2px solid var(--bc-accent);
    outline-offset: 2px;
  }
  .card {
    background: var(--bc-card);
    border: 1px solid var(--bc-border);
    border-radius: var(--bc-radius);
    box-shadow: var(--ha-card-box-shadow, none);
    overflow: hidden;
  }
  .card > h2 {
    margin: 0;
    padding: 16px 16px 4px;
    font-size: 16px;
    font-weight: 500;
  }
  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  .skeleton {
    display: block;
    border-radius: 4px;
    background: var(--bc-divider);
  }
  @media (prefers-reduced-motion: reduce) {
    *,
    *::backdrop {
      animation: none !important;
      transition: none !important;
    }
  }
`;
