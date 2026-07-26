export const CONTROLLER_TIMING = Object.freeze({
  axisPressThreshold: 0.65,
  axisReleaseThreshold: 0.35,
  initialRepeatDelayMs: 400,
  repeatIntervalMs: 140,
});

const BUTTON = Object.freeze({
  accept: 0,
  cancel: 1,
  up: 12,
  down: 13,
  left: 14,
  right: 15,
});

function pressed(pad, index) {
  return Boolean(pad.buttons[index]?.pressed);
}

function finiteAxis(pad, index) {
  const value = Number(pad.axes[index]);
  return Number.isFinite(value) ? value : 0;
}

export function updateAxisLatch(value, previous) {
  const { axisPressThreshold: press, axisReleaseThreshold: release } = CONTROLLER_TIMING;

  if (previous < 0) {
    if (value >= press) return 1;
    return value > -release ? 0 : -1;
  }
  if (previous > 0) {
    if (value <= -press) return -1;
    return value < release ? 0 : 1;
  }
  if (value <= -press) return -1;
  if (value >= press) return 1;
  return 0;
}

function buttonDirection(buttons) {
  if (buttons.up) return "up";
  if (buttons.down) return "down";
  if (buttons.left) return "left";
  if (buttons.right) return "right";
  return null;
}

function directionFor(buttons, axisX, axisY) {
  return buttonDirection(buttons)
    || (axisY < 0 ? "up" : null)
    || (axisY > 0 ? "down" : null)
    || (axisX < 0 ? "left" : null)
    || (axisX > 0 ? "right" : null);
}

function readButtons(pad) {
  return {
    accept: pressed(pad, BUTTON.accept),
    cancel: pressed(pad, BUTTON.cancel),
    up: pressed(pad, BUTTON.up),
    down: pressed(pad, BUTTON.down),
    left: pressed(pad, BUTTON.left),
    right: pressed(pad, BUTTON.right),
  };
}

function controlsAreNeutral(buttons, axisX, axisY) {
  return !Object.values(buttons).some(Boolean)
    && Math.abs(axisX) <= CONTROLLER_TIMING.axisReleaseThreshold
    && Math.abs(axisY) <= CONTROLLER_TIMING.axisReleaseThreshold;
}

function makeDeviceState(pad) {
  return {
    id: pad.id || "",
    armed: false,
    axisX: 0,
    axisY: 0,
    direction: null,
    buttonDirection: null,
    buttons: {
      accept: false,
      cancel: false,
      up: false,
      down: false,
      left: false,
      right: false,
    },
  };
}

export class ControllerInput {
  constructor({
    onDirection,
    onAccept,
    onCancel,
    now = () => performance.now(),
  }) {
    this.onDirection = onDirection;
    this.onAccept = onAccept;
    this.onCancel = onCancel;
    this.now = now;
    this.devices = new Map();
    this.activeIndex = null;
    this.repeat = { direction: null, nextAt: 0 };
  }

  reset() {
    this.devices.clear();
    this.activeIndex = null;
    this.resetRepeat();
  }

  disconnect(index) {
    this.devices.delete(index);
    if (this.activeIndex === index) {
      this.activeIndex = null;
      this.resetRepeat();
    }
  }

  poll(gamepads) {
    const present = new Set();
    const snapshots = [];

    for (const [position, pad] of gamepads.entries()) {
      if (!pad || pad.connected === false || pad.mapping !== "standard") continue;
      const index = Number.isInteger(pad.index) ? pad.index : position;
      present.add(index);
      snapshots.push(this.readStandardGamepad(pad, index));
    }

    for (const index of this.devices.keys()) {
      if (!present.has(index)) this.disconnect(index);
    }

    let selected = snapshots.find(({ index }) => index === this.activeIndex) || null;
    const digitalSwitch = snapshots.find(
      (snapshot) => snapshot.index !== this.activeIndex && snapshot.digitalActivity,
    );

    if (digitalSwitch) {
      selected = digitalSwitch;
      this.activeIndex = digitalSwitch.index;
      this.resetRepeat();
    } else if (!selected?.hasInput) {
      const newlyActive = snapshots.find((snapshot) => snapshot.newActivity);
      if (newlyActive) {
        selected = newlyActive;
        this.activeIndex = newlyActive.index;
        this.resetRepeat();
      }
    }

    if (!selected) {
      this.resetRepeat();
      return;
    }

    if (selected.acceptPressed) this.onAccept();
    if (selected.cancelPressed) this.onCancel();
    this.processDirection(selected.direction);
  }

  readStandardGamepad(pad, index) {
    let device = this.devices.get(index);
    if (!device || device.id !== (pad.id || "")) {
      device = makeDeviceState(pad);
      this.devices.set(index, device);
    }

    const buttons = readButtons(pad);
    const rawAxisX = finiteAxis(pad, 0);
    const rawAxisY = finiteAxis(pad, 1);

    if (!device.armed) {
      device.buttons = buttons;
      device.axisX = 0;
      device.axisY = 0;
      device.direction = null;
      device.buttonDirection = null;
      if (controlsAreNeutral(buttons, rawAxisX, rawAxisY)) device.armed = true;
      return {
        index,
        direction: null,
        acceptPressed: false,
        cancelPressed: false,
        digitalActivity: false,
        newActivity: false,
        hasInput: false,
      };
    }

    device.axisX = updateAxisLatch(rawAxisX, device.axisX);
    device.axisY = updateAxisLatch(rawAxisY, device.axisY);
    const nextButtonDirection = buttonDirection(buttons);
    const nextDirection = directionFor(buttons, device.axisX, device.axisY);
    const acceptPressed = buttons.accept && !device.buttons.accept;
    const cancelPressed = buttons.cancel && !device.buttons.cancel;
    const directionPressed = nextDirection !== null && nextDirection !== device.direction;
    const digitalDirectionPressed =
      nextButtonDirection !== null && nextButtonDirection !== device.buttonDirection;

    device.buttons = buttons;
    device.direction = nextDirection;
    device.buttonDirection = nextButtonDirection;

    return {
      index,
      direction: nextDirection,
      acceptPressed,
      cancelPressed,
      digitalActivity: acceptPressed || cancelPressed || digitalDirectionPressed,
      newActivity: acceptPressed || cancelPressed || directionPressed,
      hasInput: Boolean(nextDirection || buttons.accept || buttons.cancel),
    };
  }

  processDirection(direction) {
    if (!direction) {
      this.resetRepeat();
      return;
    }

    const now = this.now();
    if (this.repeat.direction !== direction) {
      this.onDirection(direction);
      this.repeat = {
        direction,
        nextAt: now + CONTROLLER_TIMING.initialRepeatDelayMs,
      };
      return;
    }

    if (now >= this.repeat.nextAt) {
      this.onDirection(direction);
      this.repeat.nextAt = now + CONTROLLER_TIMING.repeatIntervalMs;
    }
  }

  resetRepeat() {
    this.repeat = { direction: null, nextAt: 0 };
  }
}
