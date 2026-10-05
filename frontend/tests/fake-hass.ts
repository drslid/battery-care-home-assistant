import { vi } from "vitest";
import type {
  DeviceDetails,
  DeviceView,
  Patch,
  Snapshot,
  Summary,
} from "../src/api";
import type { Connection, ConnectionEvent, HomeAssistant } from "../src/types";

interface Subscription {
  callback: (message: unknown) => void;
  message: { type: string };
  options: { resubscribe?: boolean } | undefined;
  unsubscribed: boolean;
}

/** A connection that records subscriptions and lets tests push messages. */
export class FakeConnection implements Connection {
  readonly subscriptions: Subscription[] = [];
  failures = 0;
  private readonly listeners = new Map<ConnectionEvent, Set<() => void>>();

  subscribeMessage(
    callback: (message: unknown) => void,
    message: { type: string },
    options?: { resubscribe?: boolean },
  ): Promise<() => Promise<void>> {
    if (this.failures > 0) {
      this.failures -= 1;
      return Promise.reject(
        new Error("unknown_command: Battery Care is not loaded"),
      );
    }
    const subscription: Subscription = {
      callback,
      message,
      options,
      unsubscribed: false,
    };
    this.subscriptions.push(subscription);
    return Promise.resolve(() => {
      subscription.unsubscribed = true;
      return Promise.resolve();
    });
  }

  addEventListener(event: ConnectionEvent, listener: () => void): void {
    let listeners = this.listeners.get(event);
    if (listeners === undefined) {
      listeners = new Set();
      this.listeners.set(event, listeners);
    }
    listeners.add(listener);
  }

  removeEventListener(event: ConnectionEvent, listener: () => void): void {
    this.listeners.get(event)?.delete(listener);
  }

  fire(event: ConnectionEvent): void {
    for (const listener of this.listeners.get(event) ?? []) {
      listener();
    }
  }

  listenerCount(event: ConnectionEvent): number {
    return this.listeners.get(event)?.size ?? 0;
  }

  get active(): Subscription[] {
    return this.subscriptions.filter((item) => !item.unsubscribed);
  }

  /** Send a message on every active subscription. */
  send(message: unknown): void {
    for (const subscription of this.active) {
      subscription.callback(message);
    }
  }
}

export const SUMMARY: Summary = {
  total: 3,
  monitored: 3,
  healthy: 1,
  attention: 2,
  critical: 1,
  low: 1,
  not_responding: 0,
  unknown: 0,
};

export function device(overrides: Partial<DeviceView> = {}): DeviceView {
  return {
    key: "d:door",
    name: "Front Door",
    area: "Entrance",
    level: 8,
    status: "critical",
    attention: true,
    battery: { type: "CR123A", quantity: 2 },
    battery_class: "replaceable",
    importance: "important",
    ...overrides,
  };
}

export const DEVICES: DeviceView[] = [
  device(),
  device({
    key: "d:remote",
    name: "Remote",
    area: null,
    level: 64,
    status: "ok",
    attention: false,
    battery: null,
    battery_class: "unknown",
    importance: "normal",
  }),
  device({
    key: "d:smoke",
    name: "Smoke Detector",
    area: "Hall",
    level: 18,
    status: "low",
    battery: { type: "9V", quantity: 1 },
  }),
];

export function snapshot(overrides: Partial<Snapshot> = {}): Snapshot {
  return {
    api: 1,
    type: "snapshot",
    ready: true,
    summary: SUMMARY,
    devices: DEVICES,
    ...overrides,
  };
}

export function patch(devices: DeviceView[], summary = SUMMARY): Patch {
  return { api: 1, type: "patch", summary, devices };
}

export function details(overrides: Partial<DeviceDetails> = {}): DeviceDetails {
  return {
    api: 1,
    device: device(),
    integration: "Zigbee Home Automation",
    manufacturer: "Acme",
    model: "Lock 2",
    class_reason: "battery_type",
    importance_source: "suggested",
    mode: "automatic",
    alerts: true,
    low_threshold: 20,
    critical_threshold: 10,
    stable: true,
    last_report: new Date(Date.now() - 3 * 3600 * 1000).toISOString(),
    sources: [
      {
        entity_id: "sensor.front_door_battery",
        attribute: null,
        kind: "level",
        name: "Front Door Battery",
        state: "8",
      },
      {
        entity_id: "binary_sensor.front_door_battery_low",
        attribute: null,
        kind: "low",
        name: "Front Door Battery low",
        state: "on",
      },
    ],
    ...overrides,
  };
}

export function fakeHass(
  overrides: Partial<HomeAssistant> = {},
  connection = new FakeConnection(),
): HomeAssistant & { connection: FakeConnection } {
  return {
    language: "en",
    locale: { language: "en" },
    dockedSidebar: "docked",
    kioskMode: false,
    callWS: vi.fn(() => Promise.resolve(details())) as HomeAssistant["callWS"],
    ...overrides,
    connection,
  };
}
