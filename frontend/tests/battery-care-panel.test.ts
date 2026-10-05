import { afterEach, describe, expect, it, vi } from "vitest";
import { BatteryCarePanel } from "../src/battery-care-panel";
import type { HomeAssistant } from "../src/types";
import {
  FakeConnection,
  SUMMARY,
  device,
  fakeHass,
  patch,
  snapshot,
} from "./fake-hass";

interface MountOptions {
  hass?: HomeAssistant;
  narrow?: boolean;
  path?: string;
}

const flush = () =>
  new Promise((resolve) => {
    setTimeout(resolve, 0);
  });

async function mount(options: MountOptions = {}): Promise<BatteryCarePanel> {
  const panel = new BatteryCarePanel();
  panel.hass = options.hass ?? fakeHass();
  panel.narrow = options.narrow ?? false;
  panel.route = { prefix: "/battery-care", path: options.path ?? "" };
  document.body.append(panel);
  await panel.updateComplete;
  await flush();
  return panel;
}

function connectionOf(panel: BatteryCarePanel): FakeConnection {
  return panel.hass?.connection as FakeConnection;
}

async function receive(panel: BatteryCarePanel, message: unknown) {
  connectionOf(panel).send(message);
  await panel.updateComplete;
}

function root(panel: BatteryCarePanel): ShadowRoot {
  const shadowRoot = panel.shadowRoot;
  if (shadowRoot === null) {
    throw new Error("The panel has not rendered");
  }
  return shadowRoot;
}

function texts(panel: BatteryCarePanel, selector: string): string[] {
  return [...root(panel).querySelectorAll(selector)].map((element) =>
    element.textContent.replace(/\s+/g, " ").trim(),
  );
}

afterEach(() => {
  document.body.replaceChildren();
  window.history.replaceState(null, "", "/");
  vi.restoreAllMocks();
});

describe("battery-care-panel", () => {
  it("is registered once under its Home Assistant element name", () => {
    expect(customElements.get("battery-care-panel")).toBe(BatteryCarePanel);
  });

  it("shows placeholders until the first snapshot", async () => {
    const panel = await mount();
    expect(texts(panel, "[role=status]")).toEqual(["Loading batteries…"]);

    await receive(panel, snapshot());

    expect(texts(panel, ".summary h2")).toEqual(["2 batteries need attention"]);
    expect(texts(panel, "h1")).toEqual(["Battery Care"]);
  });

  it("waits for Home Assistant to start before showing an empty list", async () => {
    const panel = await mount();

    await receive(panel, snapshot({ ready: false, devices: [] }));

    expect(texts(panel, "[role=status]")).toEqual([
      "Waiting for Home Assistant to finish starting…",
    ]);
  });

  it("applies patches to the devices it has", async () => {
    const panel = await mount();
    await receive(panel, snapshot());

    await receive(
      panel,
      patch(
        [
          device({
            key: "d:remote",
            name: "Remote",
            level: 4,
            status: "critical",
          }),
        ],
        { ...SUMMARY, healthy: 0, attention: 3, critical: 2 },
      ),
    );

    expect(texts(panel, ".row-name")).toEqual([
      "Remote",
      "Front Door",
      "Smoke Detector",
    ]);
  });

  it("follows the language of Home Assistant", async () => {
    const panel = await mount({
      hass: fakeHass({ language: "fr", locale: { language: "fr" } }),
    });
    await receive(panel, snapshot());

    expect(texts(panel, ".tab")).toEqual([
      "Vue d’ensemble",
      "Toutes les batteries",
    ]);
    expect(texts(panel, ".summary h2")).toEqual([
      "2 batteries demandent votre attention",
    ]);
    // texts() turns the narrow no-break space of French into a plain one.
    expect(texts(panel, ".row-level")).toEqual(["8 %", "18 %"]);
  });

  it("lists every battery on the second tab", async () => {
    const panel = await mount({ path: "/all" });
    await receive(panel, snapshot());

    const current = root(panel).querySelector("[aria-current=page]");
    expect(current?.textContent.trim()).toBe("All batteries");
    expect(texts(panel, ".row-name")).toEqual([
      "Front Door",
      "Smoke Detector",
      "Remote",
    ]);
    const link = root(panel).querySelector<HTMLAnchorElement>("a.row");
    expect(link?.getAttribute("href")).toBe(
      "/battery-care/all?device=d%3Adoor",
    );
  });

  it("asks for a reload when the page is out of date", async () => {
    const panel = await mount();

    await receive(panel, { ...snapshot(), api: 99 });

    expect(texts(panel, "[role=alert] span")).toEqual([
      "Battery Care has been updated. Reload this page to use the new version.",
    ]);
    expect(root(panel).querySelector(".rows")).toBeNull();
  });

  it("says when Battery Care is not running", async () => {
    const connection = new FakeConnection();
    connection.failures = 1;

    const panel = await mount({ hass: fakeHass({}, connection) });
    await panel.updateComplete;

    expect(texts(panel, ".banner")).toEqual([
      "Battery Care is not running right now. This page keeps trying to reconnect.",
    ]);
  });

  it.each([
    { narrow: true, hass: {}, shown: true },
    { narrow: false, hass: {}, shown: false },
    { narrow: false, hass: { dockedSidebar: "always_hidden" }, shown: true },
    { narrow: true, hass: { kioskMode: true }, shown: false },
    {
      narrow: true,
      hass: { auth: { external: { config: { hasSidebar: true } } } },
      shown: false,
    },
  ] as const)(
    "shows the menu button as Home Assistant does: $narrow $hass",
    async ({ narrow, hass, shown }) => {
      const panel = await mount({ narrow, hass: fakeHass(hass) });

      const button =
        root(panel).querySelector<HTMLButtonElement>(".toolbar button");

      expect(button !== null).toBe(shown);
    },
  );

  it("asks Home Assistant to toggle its sidebar", async () => {
    const panel = await mount({ narrow: true });
    const listener = vi.fn();
    document.addEventListener("hass-toggle-menu", listener);

    root(panel).querySelector<HTMLButtonElement>(".toolbar button")?.click();

    expect(listener).toHaveBeenCalledOnce();
    document.removeEventListener("hass-toggle-menu", listener);
  });

  it("opens and closes the device sheet through the address", async () => {
    window.history.replaceState(null, "", "/battery-care");
    const hass = fakeHass();
    const panel = await mount({ hass });
    await receive(panel, snapshot());

    root(panel).querySelector<HTMLAnchorElement>("a.row")?.click();
    await panel.updateComplete;

    expect(window.location.search).toBe("?device=d%3Adoor");
    const sheet = root(panel).querySelector("battery-care-device-sheet");
    expect(sheet?.deviceKey).toBe("d:door");
    expect(sheet?.device?.name).toBe("Front Door");
    expect(hass.callWS).toHaveBeenCalledWith({
      type: "battery_care/device/get",
      key: "d:door",
    });

    const back = vi.spyOn(window.history, "back").mockImplementation(() => {
      window.history.replaceState(null, "", "/battery-care");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    sheet?.dispatchEvent(new CustomEvent("sheet-closed"));
    await panel.updateComplete;

    expect(back).toHaveBeenCalledOnce();
    expect(sheet?.deviceKey).toBeNull();
  });

  it("ignores new hass objects that change nothing it shows", async () => {
    const hass = fakeHass();
    const panel = await mount({ hass });
    const render = vi.spyOn(
      panel as unknown as { render: () => unknown },
      "render",
    );

    panel.hass = { ...hass };
    await panel.updateComplete;
    expect(render).not.toHaveBeenCalled();

    panel.hass = { ...hass, language: "fr" };
    await panel.updateComplete;
    expect(render).toHaveBeenCalledOnce();
  });

  it("follows a new connection and stops when removed", async () => {
    const panel = await mount();
    const first = connectionOf(panel);

    const second = new FakeConnection();
    panel.hass = fakeHass({}, second);
    await panel.updateComplete;
    await flush();
    expect(first.active).toHaveLength(0);
    expect(second.active).toHaveLength(1);

    panel.remove();
    expect(second.active).toHaveLength(0);
    expect(second.listenerCount("ready")).toBe(0);
  });
});
