import { afterEach, describe, expect, it } from "vitest";
import { BatteryCarePanel } from "../src/battery-care-panel";

async function render(language: string): Promise<BatteryCarePanel> {
  const panel = new BatteryCarePanel();
  panel.hass = { language, locale: { language } };
  document.body.append(panel);
  await panel.updateComplete;
  return panel;
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("battery-care-panel", () => {
  it("is registered once under its Home Assistant element name", () => {
    expect(customElements.get("battery-care-panel")).toBe(BatteryCarePanel);
  });

  it("shows the product name and a starting message", async () => {
    const panel = await render("en");
    expect(panel.shadowRoot?.querySelector("h1")?.textContent).toBe(
      "Battery Care",
    );
    expect(panel.shadowRoot?.querySelector("[role=status]")?.textContent).toBe(
      "Starting…",
    );
  });

  it("follows the Home Assistant language", async () => {
    const panel = await render("fr");
    expect(panel.shadowRoot?.querySelector("[role=status]")?.textContent).toBe(
      "Démarrage…",
    );
  });
});
