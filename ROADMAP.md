# aquaPi Roadmap

Unsorted idea collection - not prioritized yet. Includes unfinished
items moved over from the legacy `ToDo` file (verified against the
current code first - several original ToDo entries turned out to
already be done and were left there instead, see its DONE section) plus
items already tracked in recent working notes. Some entries below may
overlap/repeat each other - that's fine, sort/dedupe later.

## Carried over from recent working notes

- `ScaleAux` calibration/adjustment UI in general, not just pH - needs
  frontend design, not just a backend change. 2-point pH calibration
  (`aux_nodes.py`) is the motivating case (JBL's aging-probe guidance -
  reject a probe if the pH7/pH4 calibration offset exceeds ~40mV or
  their voltage diff drops below ~90mV - is a relevant reference), but
  any `ScaleAux` (offset/factor) could use the same kind of guided
  adjustment.
- Interrupt-driven IO instead of polling (`in_nodes.py`) - driver/
  architecture-level change, likely hardware-dependent.
- Systemverwaltung page (global/system-wide app preferences - driver
  accounts, blacklist) - name agreed, page not built; `config.json`
  hand-edited for now.
- Profil page (personal per-user preferences: language, theme) - name
  agreed, deliberately not built while it's only 2 settings.
- Backend i18n debt - `api.py` error messages, Dashboard's generic
  "Read error!" alert text still not localized. (Old ToDo note: use
  Python's `gettext` package for this - frontend i18n is already in
  place, this is backend-only.)
- Review data-type compatibility between every node's output and every
  node's input (e.g. `/wiring`'s "receives" dropdown currently offers
  History a STRING source) - filter by type/property, not a whitelist.
  A written plan exists at `.junie/plans/config-receives-type-filtering.md`;
  the earlier hold on it is lifted. Backend spots: `db.py:295`,
  `api.py` (existence/cardinality checks only, marked with
  `TODO(config-receives-type-filtering)`); frontend: `receivesItems` in
  `configNodeDialog.js` plus the AlertCondEditor source picker.
- Alert "reverse chip" idea - show the causing node on a triggered
  AlertCond widget; blocked on no directed bus messaging today.
- Remote Shelly + temperature add-on - paused mid-implementation,
  needs a live `/status` check to finish `_identify()` parsing.
- Rare `SunCtrl` fader thread "join before start" flake - confirmed
  environmental, not reproduced in isolation, not investigated further.
- Macro/scene architecture - a scheduled/triggered sender of messages
  on the bus, possibly needing affected nodes to suspend their own
  listening to avoid conflicts (a "MsgControl" with suspend/overrule/
  resume?) - not fully designed, still just discussion.

## Moved from the legacy ToDo file (still unfinished)

- Raspberry Pi Zero 2 W loses WLAN after some days - a known upstream
  issue (https://forums.raspberrypi.com/viewtopic.php?t=357703),
  `sudo iw wlan0 set power_save off` was tried as a workaround.
- Consider replacing `__setstate__`/`__getstate__` with `__reduce__`
  (remove per-class `__setstate__` except where a class needs to start
  threads on restore) - never done; the codebase has since leaned
  further into `__getstate__`/`__setstate__` for every new node type
  (most recently `ScheduleInput`), so this would now touch a lot of code.
- Logging to the systemd journal (see
  https://trstringer.com/systemd-logging-in-python/) - notably, the
  real production Pi (`aquapi2`) doesn't run as a systemd service at
  all today (a `./run` process kept alive in a long-lived interactive
  shell) - this idea would want that as a prerequisite.
- A `/log` route/page to view logs, warnings, and configured events -
  no such route exists yet.
- Allow (re-)configuring the app via a command-line JSON option, for
  simplified/scripted initial setup - not implemented.
- A guided setup wizard for first-time configuration, built on the
  existing Wiring editor's Templates & Snapshots feature (which already
  covers saving/restoring node-graph presets) - the wizard/guided-flow
  layer on top of it was never built.
- A "simple UI" mode for easy onboarding (e.g. hiding AUX nodes) versus
  the current "advanced" UI - not implemented, no mode toggle exists.
- New node types: a delay controller; an analog or random-value
  schedule input (today's `ScheduleInput` is binary-only); cloud
  telemetry.
- More input/output drivers: a generic file-based input, a Shelly
  *input* (distinct from the existing Shelly relay/output driver,
  which is already implemented), a PCA9685 PWM driver, a file-based
  output, and a shell-script output driver.
- Add `click`-based CLI options (e.g. `--resetfactory`, `--list`, ...)
  instead of today's plain env-var/flag-based `./run`/`./dbg` scripts.
- Known repo hygiene issue: two old QuestDB tarballs
  (`questdb-7.1.3-no-jre-bin.tar.gz`, `questdb-7.1.3-rt-linux-amd64.tar.gz`)
  are still bloating git *history* (confirmed still present via
  `git rev-list --objects --all`), even though `.gitignore` now
  prevents new ones from being tracked. Rewriting history
  (`git filter-repo`/BFG) would shrink the repo significantly but is
  destructive for a shared repo - needs an explicit, separate,
  approved pass.
- Review the `wallneradam/tc420` fork's packaging/installation as a git
  submodule (`pip install tc420`, udev rules, `plugdev` group, etc.) -
  overlaps with the already-tracked `tc420` driver work (worktree
  parked on PEP 541, tier-2 bugs already fixed) - check that backlog
  item first before treating this as new work.
- Packaging/deployment: look at how `ReefSpy`/`ReefberryPi` (GitHub)
  freeze dependencies and package for one-file deployment (PyInstaller),
  service creation, etc. - today's deployment is a manually-run
  `./run` script in a kept-open shell, not a packaged/serviced install.
- Less common feature ideas, not designed yet:
  - Multiple sensors feeding one controller for redundancy/safety.
  - Several controllers driving one output in a predictable, combined
    way.
  - Over-temperature dimming the light or spinning up a fan, e.g.
    `min(LightCtrl, clipped_inverse_scaled_temperature) -> AnalogOut`.
  - Low pH turning on the light, to let plants consume more CO2.
  - Sizing heuristics for heater/CO2-valve capacity based on observed
    utilization.
  - Support for a lux meter.

## New ideas

- Split bus - either a headless sub-bus running on a different
  system/location, coupled through bridge nodes; or two full-blown
  aquaPi systems sharing some or all of their bus traffic.
- More `AlertCond` descendants: warn for hyper/sleepy activity (a
  controller cycling too fast, or stuck on/off too long) - already has
  commented-out stubs in `alert_nodes.py` (`AlertLongActive`/
  `AlertLongInactive`, `now - _last_off/_last_on > limit`), never
  implemented.
- New `AuxNode` descendant computing a running standard deviation of
  received data, triggering when it leaves a defined range - a
  concrete approach for recommending filter cleaning based on reduced
  water flow (which increases temperature volatility), merging the
  earlier vague "filter cleaning heuristics" idea into this one.
- A node to send predefined messages (distinct from Alerts) when
  triggered - for reminders, statistics, and similar notifications that
  aren't really "alerts".
- Remove hash-based (`/#/`) routing, now that Jinja removal is done and
  no longer blocks it.
- Explore how sub-data could be allowed, i.e. nodes posting more than
  one datum on the bus, and listeners to listen to specific sub-data -
  RGB light support (below) is a concrete motivating case for this.
- RGB light support (e.g. `DriverShellyDimmer`'s sibling for
  Shelly devices' `/color/N` endpoint, not just brightness-only
  `/light/N`) - would need a new TUPLE-like MsgData range for an
  (r, g, b) triple, plus a TBD color-space controller node to emit
  it (HSV cycling, presets, etc.). Two ways to get from that tuple to
  actual hardware, both riding on the sub-data idea above: either a
  controller emits one RGB tuple and 3 separate AnalogDevice dimmer
  nodes each listen to just their own R/G/B sub-datum, or a single new
  DeviceNode receives the whole tuple and internally combines 3
  dimmer drivers (channels) into one node.

## Hardware coverage: chains and drivers (analysis 2026-09-10)

The bus carries one scalar per node (bool as 100/0, analog float, or
text) and a chain is `input(s) -> aux -> controller -> device`. Picking a
different leaf driver on an existing chain is enough only for a plain
scalar sensor (`->Ain`/`Bin`) or a plain scalar actuator (`<-Aout`/
`Bout`). Fine as-is with just a new driver: ORP probe (mV `->Ain`), float/
leak switch, heater on a relay, single-colour LED, air pump / powerhead /
UV / skimmer on-off, single PWM fan.

### Devices that need a specialized chain, not just another driver

- **A value has to be fed *into* the driver** - there is no sensor->driver
  channel today (see the `ph-control-ezo` note in the pre-ship templates
  work: an EZO-pH needs the water temperature pushed to it per read).
  Same class: EC/conductivity/TDS probes (temp compensation + cell
  constant), dissolved-oxygen probes (temp + salinity/pressure), and
  dose-to-a-target auto-dosing (meter volume until a setpoint is reached,
  with lockout). Needs an `InputNode`/driver-interface extension for a
  driver-settable compensation input.
- **Inherently multi-channel** - one "port" isn't one scalar. RGB/RGBW/
  multi-emitter LED fixtures (see the RGB light + sub-data entries above -
  this is the flagship case), and DMX/Art-Net lighting (512 channels per
  universe, needs channel grouping like an oversized TC420).
- **Pulse / count / duration semantics instead of a level** - flow meters
  (pulse output; `PortFunc` has no counter type), dosing pumps / auto-
  feeders / actuated valves / steppers ("run N ml / N s / N steps" one-
  shot action node), momentary push buttons (event vs level - see the
  Shelly-input entry and the parked `project_shelly_button_modes_bus_fit`
  note; needs a toggle/latch node).
- **Interlock / state machine / anti-short-cycle** - chiller/compressor
  (min-on and min-off time; `ThresholdCtrl` is pure hysteresis today),
  redundant ATO (dual float + fill-timeout + reservoir-low, hard-stop on
  any fault - overlaps the `AlertLongActive` idea), heater over-temp
  safety cutoff (independent high-limit overriding the PID in the output
  path), CO2 with night shutoff (pH control *gated* by the light
  schedule - needs a boolean-gate aux node, none exists).
- **A whole protocol rather than a port** - MQTT (Tasmota / Zigbee2MQTT /
  ESPHome; one bridge exposes many entities), Modbus RTU/TCP (pro
  chillers, dosers, controllers), Home Assistant / Kasa / Tuya plugs.
  Network audio already has the experimental eISCP `TextInput`/`Tout`
  path.

### Missing drivers for common hardware

Existing: GPIO, on-board PWM, DS1820, ADS1115, TC420, Shelly relay/
dimmer, Email/Telegram, eISCP (experimental).

- Sensors: other I2C ADCs (ADS1015, MCP3421, PCF8591); EZO / I2C smart
  probes (pH, EC, DO, ORP, RTD - no software calibration needed); air
  temp/humidity (BME280, SHT31, AHT20, DHT22 - canopy/room); RTD/
  thermocouple (MAX31865, MAX31855 - heater-element temp); water level
  (ultrasonic JSN-SR04T, eTape, capacitive, optical IR); pulse flow
  meter (needs a counter input); light/PAR (BH1750, TSL2591 - overlaps
  the "lux meter" idea above); current/power (INA219, INA226 - pump/
  heater failure detection); DS3231 RTC (the Pi has none, and
  `ScheduleInput`/`SunCtrl` depend on wall-clock time).
- Actuators: PCA9685 PWM expander (already listed above); GPIO/relay
  expanders (MCP23017, I2C 8-relay boards); MCP4725 DAC for true 0-10 V/
  0-5 V control (pro ballasts, chillers, DC return pumps); motor/stepper/
  servo drivers (A4988, DRV8825, TB6612 - dosers, feeders, valves);
  DMX/Art-Net; IR blaster (IR-only chillers/AC).
- Integrations: an MQTT bridge is the highest-leverage single addition;
  Home Assistant REST / Kasa / Tuya for plugs beyond Shelly; Modbus.

<!-- add items below as they come up -->
