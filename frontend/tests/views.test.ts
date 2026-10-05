import { render } from "lit";
import { afterEach, describe, expect, it } from "vitest";
import {
  byAttention,
  renderAll,
  renderOverview,
  renderSkeleton,
  type ViewContext,
} from "../src/views";
import { DEVICES, SUMMARY, device } from "./fake-hass";

const CONTEXT: ViewContext = {
  language: "en",
  locale: "en",
  deviceHref: (key) => `/battery-care?device=${encodeURIComponent(key)}`,
};

function mount(template: Parameters<typeof render>[0]): HTMLElement {
  const container = document.createElement("div");
  document.body.append(container);
  render(template, container);
  return container;
}

function texts(container: HTMLElement, selector: string): string[] {
  return [...container.querySelectorAll(selector)].map((element) =>
    element.textContent.replace(/\s+/g, " ").trim(),
  );
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("needs attention order", () => {
  it("puts the most severe, then the most important, then the lowest first", () => {
    const devices = [
      device({ key: "a", name: "A", status: "low", level: 5 }),
      device({ key: "b", name: "B", status: "not_responding", level: null }),
      device({ key: "c", name: "C", status: "critical", importance: "normal" }),
      device({
        key: "d",
        name: "D",
        status: "critical",
        importance: "critical",
      }),
      device({ key: "e", name: "E", status: "low", level: 15 }),
    ];

    expect(devices.sort(byAttention).map((item) => item.key)).toEqual([
      "d",
      "c",
      "b",
      "a",
      "e",
    ]);
  });
});

describe("overview", () => {
  it("lists what needs attention under the summary", () => {
    const container = mount(
      renderOverview(DEVICES, SUMMARY, "/battery-care/all", CONTEXT),
    );

    expect(texts(container, ".summary h2")).toEqual([
      "2 batteries need attention",
    ]);
    expect(texts(container, ".count")).toEqual([
      "Healthy 1",
      "Low 1",
      "Critical 1",
      "Not responding 0",
    ]);
    expect(texts(container, ".row-name")).toEqual([
      "Front Door",
      "Smoke Detector",
    ]);
    expect(texts(container, ".row-details")).toEqual([
      "Entrance · 2 × CR123A",
      "Hall · 9V",
    ]);
    expect(texts(container, ".row-status")).toEqual([
      "Battery critical",
      "Battery low",
    ]);
    const first = container.querySelector<HTMLAnchorElement>("a.row");
    expect(first?.getAttribute("href")).toBe("/battery-care?device=d%3Adoor");
    expect(texts(container, ".see-all")).toEqual(["See all 3 batteries"]);
  });

  it("says when everything is fine", () => {
    const healthy = {
      ...SUMMARY,
      healthy: 3,
      attention: 0,
      critical: 0,
      low: 0,
    };
    const container = mount(
      renderOverview(
        DEVICES.map((item) => ({ ...item, attention: false })),
        healthy,
        "/all",
        CONTEXT,
      ),
    );

    expect(texts(container, ".summary h2")).toEqual([
      "All batteries are healthy",
    ]);
    expect(container.querySelector(".rows")).toBeNull();
  });

  it("does not call batteries healthy when no alert is on", () => {
    const quiet = { ...SUMMARY, monitored: 0, healthy: 0, attention: 0 };
    const container = mount(renderOverview([], quiet, "/all", CONTEXT));

    expect(texts(container, ".summary h2")).toEqual([
      "Alerts are off for every battery",
    ]);
  });

  it("explains an empty home", () => {
    const empty = {
      total: 0,
      monitored: 0,
      healthy: 0,
      attention: 0,
      critical: 0,
      low: 0,
      not_responding: 0,
    };
    const container = mount(renderOverview([], empty, "/all", CONTEXT));

    expect(texts(container, "h2")).toEqual(["No batteries found yet"]);
  });
});

describe("all batteries", () => {
  it("lists every battery from the lowest level, unknown last", () => {
    const devices = [
      ...DEVICES,
      device({ key: "x", name: "Window", level: null, status: "unknown" }),
    ];
    const container = mount(renderAll(devices, CONTEXT));

    expect(texts(container, "h2")).toEqual(["4 batteries"]);
    expect(texts(container, ".row-name")).toEqual([
      "Front Door",
      "Smoke Detector",
      "Remote",
      "Window",
    ]);
    expect(texts(container, ".row-level")).toEqual(["8%", "18%", "64%"]);
  });
});

describe("skeleton", () => {
  it("announces the wait without reading out the placeholders", () => {
    const container = mount(renderSkeleton("Loading batteries…"));

    expect(texts(container, "[role=status]")).toEqual(["Loading batteries…"]);
    expect(container.querySelector(".rows")?.getAttribute("aria-hidden")).toBe(
      "true",
    );
  });
});
