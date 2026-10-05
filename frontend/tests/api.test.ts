import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Feed, RETRY_DELAYS, type FeedStatus } from "../src/api";
import { FakeConnection, patch, snapshot } from "./fake-hass";

function setup(connection = new FakeConnection()) {
  const messages: unknown[] = [];
  const statuses: FeedStatus[] = [];
  const feed = new Feed(
    connection,
    (message) => messages.push(message),
    (status) => statuses.push(status),
  );
  return { connection, feed, messages, statuses };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Feed", () => {
  it("subscribes once, without the connection's own resubscription", async () => {
    const { connection, feed, messages, statuses } = setup();

    feed.start();
    feed.start();
    await vi.runAllTimersAsync();

    expect(connection.subscriptions).toHaveLength(1);
    expect(connection.subscriptions[0]?.message).toEqual({
      type: "battery_care/subscribe",
    });
    expect(connection.subscriptions[0]?.options).toEqual({
      resubscribe: false,
    });
    connection.send(snapshot());
    connection.send(patch([]));
    expect(messages).toEqual([snapshot(), patch([])]);
    expect(statuses).toEqual(["live", "live"]);
  });

  it("retries with growing delays while Battery Care is not loaded", async () => {
    const connection = new FakeConnection();
    connection.failures = 3;
    const { feed, statuses } = setup(connection);

    feed.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(statuses).toEqual(["unavailable"]);

    await vi.advanceTimersByTimeAsync(RETRY_DELAYS[0] ?? 0);
    await vi.advanceTimersByTimeAsync((RETRY_DELAYS[1] ?? 0) - 1);
    expect(connection.subscriptions).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);
    await vi.advanceTimersByTimeAsync(RETRY_DELAYS[2] ?? 0);

    expect(connection.subscriptions).toHaveLength(1);
    connection.send(snapshot());
    expect(statuses[statuses.length - 1]).toBe("live");
  });

  it("asks for a reload when the backend speaks another version", async () => {
    const { connection, feed, messages, statuses } = setup();
    feed.start();
    await vi.advanceTimersByTimeAsync(0);

    connection.send({ ...snapshot(), api: 2 });
    await vi.runAllTimersAsync();

    expect(statuses).toEqual(["outdated"]);
    expect(messages).toEqual([]);
    expect(connection.active).toHaveLength(0);
    expect(connection.listenerCount("ready")).toBe(0);
  });

  it("subscribes again after the integration reloads", async () => {
    const { connection, feed, statuses } = setup();
    feed.start();
    await vi.advanceTimersByTimeAsync(0);

    connection.send({ api: 1, type: "closed" });
    expect(connection.active).toHaveLength(0);
    expect(statuses).toEqual(["unavailable"]);

    await vi.advanceTimersByTimeAsync(RETRY_DELAYS[0] ?? 0);
    expect(connection.active).toHaveLength(1);
  });

  it("subscribes again when the connection comes back", async () => {
    const { connection, feed, messages } = setup();
    feed.start();
    await vi.advanceTimersByTimeAsync(0);
    const first = connection.subscriptions[0];

    connection.fire("disconnected");
    connection.fire("ready");
    await vi.advanceTimersByTimeAsync(0);

    // The old subscription died with the connection: nothing to unsubscribe.
    expect(first?.unsubscribed).toBe(false);
    expect(connection.subscriptions).toHaveLength(2);
    first?.callback(snapshot());
    expect(messages).toEqual([]);
  });

  it("stops listening when stopped", async () => {
    const { connection, feed, messages } = setup();
    feed.start();
    await vi.advanceTimersByTimeAsync(0);

    feed.stop();
    feed.stop();
    connection.send(snapshot());
    connection.fire("ready");
    await vi.runAllTimersAsync();

    expect(messages).toEqual([]);
    expect(connection.subscriptions).toHaveLength(1);
    expect(connection.active).toHaveLength(0);
    expect(connection.listenerCount("disconnected")).toBe(0);
  });

  it("drops a subscription that completes after being superseded", async () => {
    const { connection, feed } = setup();

    feed.start();
    connection.fire("ready");
    await vi.advanceTimersByTimeAsync(0);

    expect(connection.subscriptions).toHaveLength(2);
    expect(connection.active).toHaveLength(1);
  });
});
