import assert from "node:assert/strict";
import test from "node:test";

import {
  CONTROLLER_TIMING,
  ControllerInput,
  updateAxisLatch,
} from "../public/static/controller.js";

function gamepad({
  index = 0,
  id = "Test Controller",
  mapping = "standard",
  axes = [0, 0],
  pressed = [],
} = {}) {
  const buttons = Array.from({ length: 16 }, (_, buttonIndex) => ({
    pressed: pressed.includes(buttonIndex),
    value: pressed.includes(buttonIndex) ? 1 : 0,
  }));
  return { index, id, mapping, axes, buttons, connected: true };
}

function harness() {
  let now = 0;
  const events = [];
  const input = new ControllerInput({
    onDirection: (direction) => events.push(direction),
    onAccept: () => events.push("accept"),
    onCancel: () => events.push("cancel"),
    now: () => now,
  });
  return {
    input,
    events,
    setNow(value) {
      now = value;
    },
  };
}

test("ignores raw non-standard wheel axes and buttons", () => {
  const { input, events, setNow } = harness();
  const wheel = gamepad({
    id: "Logitech G29 Driving Force Racing Wheel",
    mapping: "",
    axes: [0, 1],
    pressed: [13],
  });

  for (let frame = 0; frame < 120; frame += 1) {
    setNow(frame * 16);
    input.poll([wheel]);
  }

  assert.deepEqual(events, []);
});

test("uses a standard controller even when a non-standard wheel is first", () => {
  const { input, events } = harness();
  const wheel = gamepad({ index: 0, mapping: "", axes: [0, 1] });
  const controller = gamepad({ index: 1 });

  input.poll([wheel, controller]);
  input.poll([wheel, gamepad({ index: 1, pressed: [13] })]);

  assert.deepEqual(events, ["down"]);
});

test("requires neutral input before arming a standard controller", () => {
  const { input, events, setNow } = harness();
  const heldDown = gamepad({ axes: [0, 1] });

  input.poll([heldDown]);
  setNow(1000);
  input.poll([heldDown]);
  assert.deepEqual(events, []);

  input.poll([gamepad()]);
  input.poll([heldDown]);
  assert.deepEqual(events, ["down"]);
});

test("uses hysteresis so threshold noise does not release and retrigger", () => {
  assert.equal(updateAxisLatch(0.66, 0), 1);
  assert.equal(updateAxisLatch(0.5, 1), 1);
  assert.equal(updateAxisLatch(0.36, 1), 1);
  assert.equal(updateAxisLatch(0.34, 1), 0);
  assert.equal(updateAxisLatch(0.64, 0), 0);
});

test("waits for the initial delay before repeating a held direction", () => {
  const { input, events, setNow } = harness();
  input.poll([gamepad()]);
  input.poll([gamepad({ pressed: [13] })]);
  assert.deepEqual(events, ["down"]);

  setNow(CONTROLLER_TIMING.initialRepeatDelayMs - 1);
  input.poll([gamepad({ pressed: [13] })]);
  assert.deepEqual(events, ["down"]);

  setNow(CONTROLLER_TIMING.initialRepeatDelayMs);
  input.poll([gamepad({ pressed: [13] })]);
  assert.deepEqual(events, ["down", "down"]);

  setNow(
    CONTROLLER_TIMING.initialRepeatDelayMs
      + CONTROLLER_TIMING.repeatIntervalMs,
  );
  input.poll([gamepad({ pressed: [13] })]);
  assert.deepEqual(events, ["down", "down", "down"]);
});

test("accept and cancel buttons fire only on their pressed edge", () => {
  const { input, events } = harness();
  input.poll([gamepad()]);

  input.poll([gamepad({ pressed: [0] })]);
  input.poll([gamepad({ pressed: [0] })]);
  input.poll([gamepad()]);
  input.poll([gamepad({ pressed: [1] })]);

  assert.deepEqual(events, ["accept", "cancel"]);
});

test("reset requires a fresh neutral observation", () => {
  const { input, events } = harness();
  input.poll([gamepad()]);
  input.poll([gamepad({ pressed: [13] })]);
  assert.deepEqual(events, ["down"]);

  input.reset();
  input.poll([gamepad({ pressed: [13] })]);
  assert.deepEqual(events, ["down"]);
  input.poll([gamepad()]);
  input.poll([gamepad({ pressed: [13] })]);
  assert.deepEqual(events, ["down", "down"]);
});
