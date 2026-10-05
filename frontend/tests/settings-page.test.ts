import { afterEach, describe, expect, it, vi } from "vitest";
import type { TestResult } from "../src/api";
import {
  BatteryCareSettings,
  clockMinute,
  clockText,
  errorMessage,
} from "../src/settings-page";
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
      "Notifications",
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
    expect(root(page).querySelector(".test")).toBeNull();
  });

  it("lets an administrator choose the phones to notify", async () => {
    const { page, callWS } = await mount();
    const phones = () =>
      [...root(page).querySelectorAll<HTMLInputElement>(".phones input")].map(
        (element) => element.checked,
      );

    expect(texts(page, ".phones label")).toEqual([
      "iPad",
      "Pixel",
      "mobile_app_old_phone (not found)",
    ]);
    expect(phones()).toEqual([false, true, true]);

    change(input(page, "iPad"), true);
    await settle(page);
    change(input(page, "mobile_app_old_phone (not found)"), false);
    await settle(page);

    expect(
      sent(callWS, "battery_care/settings/update").map(
        ({ changes }) => changes,
      ),
    ).toEqual([
      {
        notify_targets: [
          "mobile_app_pixel",
          "mobile_app_old_phone",
          "mobile_app_ipad",
        ],
      },
      { notify_targets: ["mobile_app_pixel", "mobile_app_ipad"] },
    ]);
    expect(phones()).toEqual([true, true, false]);
  });

  it("says when no phone has the Home Assistant app", async () => {
    const view = settingsView({ targets: [] });
    const callWS = backend({ "battery_care/settings/get": () => view });
    const { page } = await mount({ callWS });

    expect(texts(page, ".phones p")).toEqual([
      "No phone or tablet has the Home Assistant app.",
    ]);
  });

  it("saves times as minutes after midnight", async () => {
    const { page, callWS } = await mount();
    const summary = input(page, "Daily summary at");
    expect(summary.value).toBe("18:00");
    expect(input(page, "Quiet from").value).toBe("22:00");

    change(summary, "");
    await settle(page);
    expect(sent(callWS, "battery_care/settings/update")).toEqual([]);
    expect(summary.value).toBe("18:00");

    change(summary, "07:30");
    change(input(page, "Quiet hours"), false);
    await settle(page);

    expect(
      sent(callWS, "battery_care/settings/update").map(
        ({ changes }) => changes,
      ),
    ).toEqual([{ digest_minute: 450 }, { quiet_hours: false }]);
    expect(texts(page, "label.field span")).not.toContain("Quiet from");
  });

  it("sends a test notification and says what it reached", async () => {
    let answer: (result: TestResult) => void = () => undefined;
    const callWS = backend({
      "battery_care/notify/test": () =>
        new Promise((resolve) => {
          answer = resolve;
        }),
    });
    const { page } = await mount({ callWS });
    const button = () =>
      root(page).querySelector<HTMLButtonElement>(".test button");

    button()?.click();
    await settle(page);
    expect(button()?.disabled).toBe(true);

    answer({
      persistent: true,
      phones: [
        { service: "mobile_app_pixel", name: "Pixel", error: null },
        { service: "mobile_app_ipad", name: "iPad", error: "timeout" },
      ],
    });
    await settle(page);

    expect(button()?.disabled).toBe(false);
    expect(texts(page, ".test [role=status]")).toEqual([
      "Test notification sent.",
    ]);
    expect(texts(page, ".test [role=alert]")).toEqual([
      "iPad could not be notified.",
    ]);

    button()?.click();
    answer({ persistent: false, phones: [] });
    await settle(page);

    expect(texts(page, ".test [role=status]")).toEqual([
      "Nothing was sent: turn on Home Assistant notifications or choose a phone.",
    ]);
    expect(texts(page, ".test [role=alert]")).toEqual([]);
  });

  it("explains a test notification that could not be sent", async () => {
    const callWS = backend({
      "battery_care/notify/test": () => Promise.reject(new Error("timeout")),
    });
    const { page } = await mount({ callWS });

    root(page).querySelector<HTMLButtonElement>(".test button")?.click();
    await settle(page);

    expect(texts(page, "[role=alert]")).toEqual([
      "This change could not be saved.",
    ]);
    expect(
      root(page).querySelector<HTMLButtonElement>(".test button")?.disabled,
    ).toBe(false);
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
    expect(
      errorMessage(error("quiet_end_minute: quiet_hours_empty"), "fr"),
    ).toBe(
      "Les heures calmes doivent se terminer à une autre heure que leur début.",
    );
    expect(errorMessage(error("notify_targets: invalid_targets"), "en")).toBe(
      "These phones cannot be notified.",
    );
    expect(errorMessage("not an error", "en")).toBe(
      "This change could not be saved.",
    );
  });
});

describe("clock", () => {
  it("turns minutes after midnight into HH:MM and back", () => {
    expect(clockText(0)).toBe("00:00");
    expect(clockText(450)).toBe("07:30");
    expect(clockText(1439)).toBe("23:59");
    expect(clockMinute("07:30")).toBe(450);
    expect(clockMinute("23:59:30")).toBe(1439);
    for (const text of ["", "7:30", "24:00", "12:60", "noon"]) {
      expect(clockMinute(text)).toBeUndefined();
    }
  });
});
