import { afterEach, describe, expect, it, vi } from "vitest";
import { BatteryCareSettings, errorMessage } from "../src/settings-page";
import type { HomeAssistant } from "../src/types";
import { LIMITS, details, fakeHass, settingsView } from "./fake-hass";

interface Message {
  type: string;
  [key: string]: unknown;
}
type Handler = (message: Message) => unknown;

const flush = () =>
  new Promise((resolve) => {
    setTimeout(resolve, 0);
  });

/** A backend that answers every command the page sends, unless told otherwise. */
function backend(handlers: Record<string, Handler> = {}) {
  let view = settingsView();
  const defaults: Record<string, Handler> = {
    "battery_care/settings/get": () => view,
    "battery_care/settings/update": (message) => {
      view = {
        ...view,
        settings: { ...view.settings, ...(message.changes as object) },
      };
      return view;
    },
    "battery_care/class/update": (message) => {
      view = {
        ...view,
        classes: view.classes.map((row) =>
          row.battery_class === message.battery_class
            ? { ...row, custom: true, ...(message.changes as object) }
            : row,
        ),
      };
      return view;
    },
    "battery_care/device/get": () =>
      details({ chosen_class: "ups", chosen_importance: "critical" }),
    "battery_care/device/update": () => {
      view = { ...view, ignored: [] };
      return details();
    },
  };
  return vi.fn((message: Message) => {
    const handler = handlers[message.type] ?? defaults[message.type];
    return Promise.resolve(handler?.(message));
  });
}

async function mount(
  options: { admin?: boolean; language?: "en" | "fr"; callWS?: unknown } = {},
) {
  const page = new BatteryCareSettings();
  const callWS = options.callWS ?? backend();
  page.hass = fakeHass({
    user: { is_admin: options.admin ?? true },
    callWS: callWS as HomeAssistant["callWS"],
  });
  page.language = options.language ?? "en";
  page.deviceHref = (key) => `/battery-care/settings?device=${key}`;
  document.body.append(page);
  await settle(page);
  return { page, callWS: callWS as ReturnType<typeof backend> };
}

async function settle(page: BatteryCareSettings) {
  await page.updateComplete;
  await flush();
  await page.updateComplete;
}

function root(page: BatteryCareSettings): ShadowRoot {
  if (page.shadowRoot === null) {
    throw new Error("The page has not rendered");
  }
  return page.shadowRoot;
}

function texts(page: BatteryCareSettings, selector: string): string[] {
  return [...root(page).querySelectorAll(selector)].map((element) =>
    element.textContent.replace(/\s+/g, " ").trim(),
  );
}

function input(page: BatteryCareSettings, label: string): HTMLInputElement {
  const field = [...root(page).querySelectorAll("label.field")].find(
    (element) => element.querySelector("span")?.textContent.trim() === label,
  );
  const element = field?.querySelector("input");
  if (!element) {
    throw new Error(`No field labelled ${label}`);
  }
  return element;
}

function classToggle(page: BatteryCareSettings, name: string) {
  const row = [...root(page).querySelectorAll(".class-row")].find(
    (element) =>
      element.querySelector(".class-name span")?.textContent.trim() === name,
  );
  const element = row?.querySelector("input[type=checkbox]");
  if (!(element instanceof HTMLInputElement)) {
    throw new Error(`No battery type named ${name}`);
  }
  return element;
}

function change(element: HTMLInputElement, value: string | boolean) {
  if (typeof value === "boolean") {
    element.checked = value;
  } else {
    element.value = value;
  }
  element.dispatchEvent(new Event("change"));
}

function sent(callWS: ReturnType<typeof backend>, type: string): Message[] {
  return callWS.mock.calls
    .map(([message]) => message)
    .filter((message) => message.type === type);
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("settings page", () => {
  it("is registered once under its element name", () => {
    expect(customElements.get("battery-care-settings")).toBe(
      BatteryCareSettings,
    );
  });

  it("shows alerts by battery type, general settings and ignored batteries", async () => {
    const { page } = await mount();

    expect(texts(page, "h2")).toEqual([
      "Alerts by battery type",
      "Alerts and reminders",
      "Advanced",
      "Ignored batteries",
    ]);
    expect(texts(page, ".class-name")).toEqual([
      "Replaceable 2 batteries",
      "UPS 1 battery",
      "Robot 0 batteries",
    ]);
    expect(input(page, "Remind every").value).toBe("24");
    expect(input(page, "Remind every").min).toBe("6");
    expect(texts(page, ".ignored li")).toEqual(["Remote Stop ignoring"]);
    expect(root(page).querySelector(".ignored a")?.getAttribute("href")).toBe(
      "/battery-care/settings?device=d:remote",
    );
    expect(root(page).querySelector("[role=alert]")).toBeNull();
  });

  it("has a text for every label, in every language", async () => {
    for (const language of ["en", "fr"] as const) {
      const { page } = await mount({ language });
      expect(root(page).textContent).not.toMatch(
        /\b(settings|class|customize)\.[a-z_]+/,
      );
      page.remove();
    }
  });

  it("saves a battery type change at once", async () => {
    const { page, callWS } = await mount();

    change(classToggle(page, "Robot"), true);
    await settle(page);

    expect(sent(callWS, "battery_care/class/update")).toEqual([
      {
        type: "battery_care/class/update",
        battery_class: "robot",
        changes: { alerts_enabled: true },
      },
    ]);
    expect(classToggle(page, "Robot").checked).toBe(true);
  });

  it("saves a general setting and ignores what is not a whole number", async () => {
    const { page, callWS } = await mount();

    change(input(page, "Remind every"), "12.5");
    await settle(page);
    expect(sent(callWS, "battery_care/settings/update")).toEqual([]);
    expect(input(page, "Remind every").value).toBe("24");

    change(input(page, "Remind every"), "48");
    change(input(page, "Battery Care alerts"), false);
    await settle(page);

    expect(sent(callWS, "battery_care/settings/update")).toEqual([
      {
        type: "battery_care/settings/update",
        changes: { reminder_hours: 48 },
      },
      {
        type: "battery_care/settings/update",
        changes: { alerts_enabled: false },
      },
    ]);
  });

  it("explains a refused change and shows the stored value again", async () => {
    const callWS = backend({
      "battery_care/settings/update": () =>
        Promise.reject(new Error("reminder_hours: out_of_range")),
    });
    const { page } = await mount({ callWS });

    change(input(page, "Remind every"), "2");
    await settle(page);

    expect(texts(page, "[role=alert]")).toEqual([
      "Choose a value between 6 and 720.",
    ]);
    expect(input(page, "Remind every").value).toBe("24");
  });

  it("only shows the settings to a user who is not an administrator", async () => {
    const { page } = await mount({ admin: false });

    expect(texts(page, ".message")).toEqual([
      "Only an administrator can change these settings.",
    ]);
    const inputs = [...root(page).querySelectorAll("input")];
    expect(inputs.length).toBeGreaterThan(0);
    expect(inputs.every((element) => element.disabled)).toBe(true);
    expect(root(page).querySelector(".ignored button")).toBeNull();
  });

  it("stops ignoring a battery and keeps what was chosen for it", async () => {
    const { page, callWS } = await mount();

    root(page).querySelector<HTMLButtonElement>(".ignored button")?.click();
    await settle(page);
    await settle(page);

    expect(sent(callWS, "battery_care/device/update")).toEqual([
      {
        type: "battery_care/device/update",
        key: "d:remote",
        mode: "automatic",
        importance: "critical",
        battery_class: "ups",
      },
    ]);
    expect(texts(page, ".card:last-of-type p")).toEqual([
      "No battery is ignored. Open a battery to ignore it.",
    ]);
  });

  it("loads again when a battery was saved elsewhere", async () => {
    const { page, callWS } = await mount();
    expect(sent(callWS, "battery_care/settings/get")).toHaveLength(1);

    page.revision = 1;
    await settle(page);

    expect(sent(callWS, "battery_care/settings/get")).toHaveLength(2);
  });

  it("says when the settings could not be loaded", async () => {
    const callWS = vi.fn(() => Promise.reject(new Error("unknown_command")));
    const { page } = await mount({ callWS });

    expect(texts(page, ".message")).toEqual([
      "The settings could not be loaded.",
    ]);
  });
});

describe("errorMessage", () => {
  it("turns the error code into a sentence", () => {
    const error = (message: string) => new Error(message);
    expect(
      errorMessage(error("critical_threshold: critical_not_below_low"), "fr"),
    ).toBe("Le seuil critique doit être inférieur au seuil faible.");
    expect(errorMessage(error("stale_days: out_of_range"), "en", LIMITS)).toBe(
      "Choose a value between 1 and 90.",
    );
    expect(errorMessage(error("stale_days: out_of_range"), "en")).toBe(
      "This value is outside the allowed range.",
    );
    expect(errorMessage(error("timeout"), "en")).toBe(
      "This change could not be saved.",
    );
    expect(errorMessage("not an error", "en")).toBe(
      "This change could not be saved.",
    );
  });
});
