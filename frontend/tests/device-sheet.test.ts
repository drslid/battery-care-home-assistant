import { afterEach, describe, expect, it, vi } from "vitest";
import type { DeviceDetails, DeviceView } from "../src/api";
import { BatteryCareDeviceSheet } from "../src/device-sheet";
import type { HomeAssistant } from "../src/types";
import { details, device, fakeHass } from "./fake-hass";

interface SheetOptions {
  hass?: HomeAssistant;
  deviceKey?: string | null;
  device?: DeviceView | undefined;
  ready?: boolean;
}

const flush = () =>
  new Promise((resolve) => {
    setTimeout(resolve, 0);
  });

async function mount(options: SheetOptions = {}) {
  const sheet = new BatteryCareDeviceSheet();
  sheet.hass = options.hass ?? fakeHass();
  sheet.deviceKey =
    options.deviceKey === undefined ? "d:door" : options.deviceKey;
  sheet.device = "device" in options ? options.device : device();
  sheet.ready = options.ready ?? true;
  document.body.append(sheet);
  await sheet.updateComplete;
  await flush();
  await sheet.updateComplete;
  return sheet;
}

function hassWith(result: Partial<DeviceDetails>): HomeAssistant {
  return fakeHass({
    callWS: vi.fn(() =>
      Promise.resolve(details(result)),
    ) as HomeAssistant["callWS"],
  });
}

function dialog(sheet: BatteryCareDeviceSheet): HTMLDialogElement {
  const element = sheet.shadowRoot?.querySelector("dialog");
  if (!element) {
    throw new Error("The sheet has not rendered");
  }
  return element;
}

function texts(sheet: BatteryCareDeviceSheet, selector: string): string[] {
  return [...(sheet.shadowRoot?.querySelectorAll(selector) ?? [])].map(
    (element) => element.textContent.replace(/\s+/g, " ").trim(),
  );
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("device sheet", () => {
  it("shows the device, its policy and the entities used", async () => {
    const hass = fakeHass();
    const sheet = await mount({ hass });

    expect(dialog(sheet).open).toBe(true);
    expect(hass.callWS).toHaveBeenCalledWith({
      type: "battery_care/device/get",
      key: "d:door",
    });
    expect(texts(sheet, "h2")).toEqual(["Front Door"]);
    expect(texts(sheet, ".subtitle")).toEqual([
      "Entrance · Zigbee Home Automation",
    ]);
    expect(texts(sheet, ".hero")).toEqual(["8% Battery critical"]);
    expect(texts(sheet, ".fact")).toEqual([
      "Battery 2 × CR123A",
      "Last report 3 hours ago",
      "Category Replaceable · detected from its battery type",
      "Importance Important (suggested)",
      "Alerts Automatic · low at 20%, critical at 10%",
    ]);
    expect(texts(sheet, ".sources li")).toEqual([
      "Front Door Battery Level · 8% sensor.front_door_battery",
      "Front Door Battery low Low battery · Low binary_sensor.front_door_battery_low",
    ]);
  });

  it("refreshes the details when the device changes", async () => {
    const hass = fakeHass();
    const sheet = await mount({ hass });

    sheet.device = device({ level: 7 });
    await sheet.updateComplete;

    expect(hass.callWS).toHaveBeenCalledTimes(2);
    expect(texts(sheet, ".hero-level")).toEqual(["7%"]);
  });

  it("says when the battery is gone", async () => {
    const sheet = await mount({ device: undefined });
    expect(texts(sheet, ".message")).toEqual([
      "This battery is no longer in Home Assistant.",
    ]);

    sheet.ready = false;
    await sheet.updateComplete;
    expect(texts(sheet, ".message")).toEqual(["Loading batteries…"]);
  });

  it("says when the details could not be loaded", async () => {
    const hass = fakeHass({
      callWS: vi.fn(() => Promise.reject(new Error("not_found"))),
    });

    const sheet = await mount({ hass });

    expect(texts(sheet, ".message")).toEqual([
      "The details could not be loaded.",
    ]);
  });

  it("reports a close, but not when the address closed it", async () => {
    const sheet = await mount();
    const closed = vi.fn();
    sheet.addEventListener("sheet-closed", closed);

    sheet.shadowRoot?.querySelector<HTMLButtonElement>(".icon-button")?.click();
    await flush();
    expect(closed).toHaveBeenCalledOnce();

    sheet.deviceKey = "d:door";
    await sheet.updateComplete;
    dialog(sheet).showModal();
    sheet.deviceKey = null;
    await sheet.updateComplete;
    await flush();
    expect(dialog(sheet).open).toBe(false);
    expect(closed).toHaveBeenCalledOnce();
  });

  it("closes on a click on the backdrop only", async () => {
    const sheet = await mount();
    const closed = vi.fn();
    sheet.addEventListener("sheet-closed", closed);

    sheet.shadowRoot?.querySelector("h2")?.click();
    await flush();
    expect(closed).not.toHaveBeenCalled();

    dialog(sheet).click();
    await flush();
    expect(closed).toHaveBeenCalledOnce();
  });

  it.each([
    [{ mode: "ignored", alerts: false }, "Off · this battery is ignored"],
    [{ mode: "automatic", alerts: false }, "Off"],
    [
      { mode: "custom", low_threshold: 30 },
      "Custom · low at 30%, critical at 10%",
    ],
  ] as const)("explains the alerts: %o", async (result, expected) => {
    const sheet = await mount({ hass: hassWith(result) });

    const facts = texts(sheet, ".fact");
    expect(facts[facts.length - 1]).toBe(`Alerts ${expected}`);
  });

  it("explains what it cannot know", async () => {
    const sheet = await mount({
      device: device({ battery: null, level: null, status: "unknown" }),
      hass: hassWith({
        last_report: null,
        importance_source: "default",
        stable: false,
        sources: [
          {
            entity_id: "a",
            attribute: null,
            kind: "level",
            name: "A",
            state: "unavailable",
          },
          {
            entity_id: "b",
            attribute: null,
            kind: "level",
            name: "B",
            state: null,
          },
          {
            entity_id: "c",
            attribute: null,
            kind: "level",
            name: "C",
            state: "bad",
          },
          {
            entity_id: "d",
            attribute: null,
            kind: "charging",
            name: "D",
            state: "off",
          },
          {
            entity_id: "e",
            attribute: null,
            kind: "low",
            name: "E",
            state: "weird",
          },
          {
            entity_id: "lock.f",
            attribute: "battery_state",
            kind: "state",
            name: "F",
            state: "Low",
          },
        ],
      }),
    });

    expect(texts(sheet, ".hero")).toEqual(["No data yet"]);
    expect(texts(sheet, ".fact")).toEqual([
      "Battery Not set",
      "Last report Never",
      "Category Replaceable · detected from its battery type",
      "Importance Important",
      "Alerts Automatic · low at 20%, critical at 10%",
    ]);
    expect(texts(sheet, ".message")).toEqual([
      "This battery has no unique ID in Home Assistant. If its entity is renamed, Battery Care sees a new battery.",
    ]);
    expect(texts(sheet, ".sources li .secondary:not(code)")).toEqual([
      "Level · Unavailable",
      "Level · Unknown",
      "Level · bad",
      "Charging · Not charging",
      "Low battery · weird",
      "Battery state · Low",
    ]);
    const codes = texts(sheet, ".sources li code");
    expect(codes[codes.length - 1]).toBe("lock.f · battery_state");
  });
});
