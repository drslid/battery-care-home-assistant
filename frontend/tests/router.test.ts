import { afterEach, describe, expect, it, vi } from "vitest";
import {
  devicePath,
  followLink,
  leaveTo,
  navigate,
  parseLocation,
  viewPath,
} from "../src/router";

afterEach(() => {
  window.history.replaceState(null, "", "/");
  vi.restoreAllMocks();
});

describe("parseLocation", () => {
  it("reads the view from the path below the panel", () => {
    expect(parseLocation("", "").view).toBe("overview");
    expect(parseLocation("/all", "").view).toBe("all");
    expect(parseLocation("/all/", "").view).toBe("all");
    expect(parseLocation("/settings", "").view).toBe("overview");
  });

  it("reads the device from the query", () => {
    expect(parseLocation("", "?device=d%3Aabc").device).toBe("d:abc");
    expect(parseLocation("", "?device=").device).toBeNull();
    expect(parseLocation("", "").device).toBeNull();
  });
});

describe("paths", () => {
  it("build links that survive a reload", () => {
    expect(viewPath("/battery-care", "overview")).toBe("/battery-care");
    expect(viewPath("/battery-care", "all")).toBe("/battery-care/all");
    expect(devicePath("/battery-care", "all", "s:sensor.a b")).toBe(
      "/battery-care/all?device=s%3Asensor.a+b",
    );
  });
});

describe("navigate", () => {
  it("pushes like Home Assistant and tells its router", () => {
    window.history.replaceState(null, "", "/battery-care");
    const listener = vi.fn();
    window.addEventListener("location-changed", listener);

    navigate("/battery-care?device=d%3Aabc");

    expect(window.location.pathname + window.location.search).toBe(
      "/battery-care?device=d%3Aabc",
    );
    expect(window.history.state).toEqual({ from: "/battery-care" });
    expect(listener).toHaveBeenCalledOnce();
    window.removeEventListener("location-changed", listener);
  });

  it("can replace the current entry", () => {
    window.history.replaceState({ from: "/lovelace" }, "", "/battery-care");

    navigate("/battery-care/all", true);

    expect(window.location.pathname).toBe("/battery-care/all");
    expect(window.history.state).toEqual({ from: "/lovelace" });
  });
});

describe("leaveTo", () => {
  it("goes back to the page the sheet was opened from", () => {
    window.history.replaceState(
      { from: "/battery-care" },
      "",
      "/battery-care?device=x",
    );
    const back = vi.spyOn(window.history, "back").mockImplementation(() => {
      // Going back is the browser's business.
    });

    leaveTo("/battery-care");

    expect(back).toHaveBeenCalledOnce();
  });

  it("replaces a deep link instead of leaving the panel", () => {
    window.history.replaceState(
      { from: "/lovelace" },
      "",
      "/battery-care?device=x",
    );
    const back = vi.spyOn(window.history, "back");

    leaveTo("/battery-care");

    expect(back).not.toHaveBeenCalled();
    expect(window.location.pathname + window.location.search).toBe(
      "/battery-care",
    );
  });
});

describe("followLink", () => {
  it("handles plain clicks and leaves the others to the browser", () => {
    window.history.replaceState(null, "", "/battery-care");
    const plain = new MouseEvent("click", { button: 0, cancelable: true });
    const newTab = new MouseEvent("click", {
      button: 0,
      ctrlKey: true,
      cancelable: true,
    });

    followLink(newTab, "/battery-care/all");
    expect(newTab.defaultPrevented).toBe(false);
    expect(window.location.pathname).toBe("/battery-care");

    followLink(plain, "/battery-care/all");
    expect(plain.defaultPrevented).toBe(true);
    expect(window.location.pathname).toBe("/battery-care/all");
  });
});
