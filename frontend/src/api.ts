import type { Connection } from "./types";

/** Must match API_VERSION in the backend; a mismatch means a stale page. */
export const API_VERSION = 1;

export type Status =
  | "critical"
  | "low"
  | "not_responding"
  | "stale"
  | "charging"
  | "ok"
  | "unknown"
  | "ignored";

export type BatteryClass =
  | "replaceable"
  | "rechargeable"
  | "robot"
  | "vehicle"
  | "ups"
  | "home_battery"
  | "unknown";

export type Importance = "low" | "normal" | "important" | "critical";

export interface Battery {
  type: string;
  quantity: number;
}

/** One battery device as the backend presents it; the frontend decides nothing. */
export interface DeviceView {
  key: string;
  name: string;
  area: string | null;
  level: number | null;
  status: Status;
  attention: boolean;
  battery: Battery | null;
  battery_class: BatteryClass;
  importance: Importance;
}

export interface Summary {
  total: number;
  monitored: number;
  healthy: number;
  attention: number;
  critical: number;
  low: number;
  not_responding: number;
  unknown: number;
}

export interface Snapshot {
  api: number;
  type: "snapshot";
  ready: boolean;
  summary: Summary;
  devices: DeviceView[];
}

export interface Patch {
  api: number;
  type: "patch";
  summary: Summary;
  devices: DeviceView[];
}

interface Closed {
  api: number;
  type: "closed";
}

type FeedMessage = Snapshot | Patch | Closed;

export type SourceKind = "level" | "low" | "charging" | "state";

export interface Source {
  entity_id: string;
  attribute: string | null;
  kind: SourceKind;
  name: string;
  state: string | null;
}

export interface DeviceDetails {
  api: number;
  device: DeviceView;
  integration: string | null;
  manufacturer: string | null;
  model: string | null;
  class_reason: string;
  importance_source: "user" | "suggested" | "default";
  mode: DeviceMode;
  alerts: boolean;
  low_threshold: number;
  critical_threshold: number;
  overrides: Partial<Settings>;
  inherited: Partial<Settings>;
  detected_class: BatteryClass;
  chosen_class: BatteryClass | null;
  suggested_importance: Importance;
  chosen_importance: Importance | null;
  limits: Limits;
  stable: boolean;
  last_report: string | null;
  snoozed_until: string | null;
  sources: Source[];
}

export type DeviceMode = "automatic" | "custom" | "ignored";

/** The global settings, as the backend names them. */
export interface Settings {
  alerts_enabled: boolean;
  low_threshold: number;
  critical_threshold: number;
  hysteresis: number;
  binary_recovery_minutes: number;
  reminder_hours: number;
  unavailable_alerts: boolean;
  unavailable_grace_hours: number;
  stale_detection: boolean;
  stale_days: number;
  persistent_notifications: boolean;
  notify_targets: string[];
  notify_recovered: boolean;
  /** Minutes after midnight, local time. */
  digest_minute: number;
  quiet_hours: boolean;
  quiet_start_minute: number;
  quiet_end_minute: number;
}

export interface ClassRow {
  battery_class: BatteryClass;
  devices: number;
  custom: boolean;
  alerts_enabled: boolean;
  low_threshold: number;
  critical_threshold: number;
}

/** The smallest and largest value allowed for each numeric setting. */
export type Limits = Partial<Record<keyof Settings, [number, number]>>;

export interface SettingsView {
  api: number;
  settings: Settings;
  limits: Limits;
  /** Phones with the Home Assistant app; chosen ones that are gone too. */
  targets: Target[];
  classes: ClassRow[];
  ignored: { key: string; name: string }[];
}

export interface Target {
  service: string;
  name: string;
  available: boolean;
}

export interface TestResult {
  persistent: boolean;
  phones: { service: string; name: string; error: string | null }[];
}

/** Waiting, receiving, Battery Care not running, or this page is out of date. */
export type FeedStatus = "connecting" | "live" | "unavailable" | "outdated";

export const RETRY_DELAYS = [1000, 2000, 5000, 10000, 30000];

/**
 * Follows `battery_care/subscribe` across reconnections and integration reloads.
 *
 * The connection's own resubscription is off: it gives up silently when the
 * command fails, which happens while Home Assistant is still starting.
 */
export class Feed {
  private unsubscribe: (() => Promise<void>) | undefined;
  private retryTimer: ReturnType<typeof setTimeout> | undefined;
  private attempts = 0;
  private generation = 0;
  private running = false;

  constructor(
    private readonly connection: Connection,
    private readonly onMessage: (message: Snapshot | Patch) => void,
    private readonly onStatus: (status: FeedStatus) => void,
  ) {}

  start(): void {
    if (this.running) {
      return;
    }
    this.running = true;
    this.connection.addEventListener("ready", this.handleReady);
    this.connection.addEventListener("disconnected", this.handleDisconnected);
    void this.subscribe();
  }

  stop(): void {
    if (!this.running) {
      return;
    }
    this.running = false;
    this.generation += 1;
    this.connection.removeEventListener("ready", this.handleReady);
    this.connection.removeEventListener(
      "disconnected",
      this.handleDisconnected,
    );
    this.clearRetry();
    this.release();
  }

  private readonly handleReady = (): void => {
    this.clearRetry();
    void this.subscribe();
  };

  private readonly handleDisconnected = (): void => {
    // The subscription ended with the connection; nothing to unsubscribe.
    this.generation += 1;
    this.unsubscribe = undefined;
  };

  private async subscribe(): Promise<void> {
    this.release();
    const generation = ++this.generation;
    try {
      const unsubscribe = await this.connection.subscribeMessage(
        (message) => {
          if (generation === this.generation) {
            // The api version check comes first in receive().
            this.receive(message as FeedMessage);
          }
        },
        { type: "battery_care/subscribe" },
        { resubscribe: false },
      );
      if (generation !== this.generation) {
        void unsubscribe().catch(() => undefined);
        return;
      }
      this.unsubscribe = unsubscribe;
    } catch {
      if (generation === this.generation) {
        this.onStatus("unavailable");
        this.retry();
      }
    }
  }

  private receive(message: FeedMessage): void {
    if (message.api !== API_VERSION) {
      this.stop();
      this.onStatus("outdated");
      return;
    }
    if (message.type === "closed") {
      this.release();
      this.onStatus("unavailable");
      this.retry();
      return;
    }
    this.attempts = 0;
    this.onStatus("live");
    this.onMessage(message);
  }

  private release(): void {
    const unsubscribe = this.unsubscribe;
    this.unsubscribe = undefined;
    if (unsubscribe) {
      void unsubscribe().catch(() => undefined);
    }
  }

  private retry(): void {
    this.clearRetry();
    const delay =
      RETRY_DELAYS[Math.min(this.attempts, RETRY_DELAYS.length - 1)] ?? 30000;
    this.attempts += 1;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = undefined;
      void this.subscribe();
    }, delay);
  }

  private clearRetry(): void {
    if (this.retryTimer !== undefined) {
      clearTimeout(this.retryTimer);
      this.retryTimer = undefined;
    }
  }
}
