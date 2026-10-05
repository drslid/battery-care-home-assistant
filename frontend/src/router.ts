export type View = "overview" | "all" | "settings";

export interface PanelLocation {
  view: View;
  device: string | null;
}

/** Read the view from the path below the panel, and the device from the query. */
export function parseLocation(path: string, search: string): PanelLocation {
  const segment = path.split("/").find((part) => part !== "") ?? "";
  const device = new URLSearchParams(search).get("device");
  return {
    view: segment === "all" || segment === "settings" ? segment : "overview",
    device: device === "" ? null : device,
  };
}

export function viewPath(prefix: string, view: View): string {
  return view === "overview" ? prefix : `${prefix}/${view}`;
}

export function devicePath(prefix: string, view: View, key: string): string {
  const query = new URLSearchParams({ device: key }).toString();
  return `${viewPath(prefix, view)}?${query}`;
}

function currentPath(): string {
  return `${window.location.pathname}${window.location.search}`;
}

/**
 * Navigate as Home Assistant does: its router follows `location-changed`, and
 * `from` in the history state tells where the back button leads.
 */
export function navigate(path: string, replace = false): void {
  const { history } = window;
  if (replace) {
    history.replaceState(history.state as unknown, "", path);
  } else {
    history.pushState({ from: currentPath() }, "", path);
  }
  window.dispatchEvent(
    new CustomEvent("location-changed", { detail: { replace } }),
  );
}

/** Go to `path`, going back when that is the page we came from. */
export function leaveTo(path: string): void {
  const state = window.history.state as { from?: unknown } | null;
  if (state?.from === path) {
    window.history.back();
  } else {
    navigate(path, true);
  }
}

/** Follow a plain click on a link in place; let the browser open new tabs. */
export function followLink(event: MouseEvent, path: string): void {
  if (
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey
  ) {
    return;
  }
  event.preventDefault();
  navigate(path);
}
