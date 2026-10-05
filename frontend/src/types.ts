/** The Home Assistant WebSocket connection, as far as the panel uses it. */
export interface Connection {
  subscribeMessage(
    callback: (message: unknown) => void,
    message: { type: string },
    options?: { resubscribe?: boolean },
  ): Promise<() => Promise<void>>;
  addEventListener(event: ConnectionEvent, listener: () => void): void;
  removeEventListener(event: ConnectionEvent, listener: () => void): void;
}

export type ConnectionEvent = "ready" | "disconnected";

/** The part of Home Assistant's `hass` object that the panel reads. */
export interface HomeAssistant {
  language: string;
  locale?: { language: string };
  connection: Connection;
  callWS: <T>(message: { type: string; [key: string]: unknown }) => Promise<T>;
  dockedSidebar?: "docked" | "always_hidden" | "auto";
  kioskMode?: boolean;
  auth?: { external?: { config?: { hasSidebar?: boolean } } };
}

/** Where Home Assistant mounted the panel, and the path below it. */
export interface Route {
  prefix: string;
  path: string;
}
