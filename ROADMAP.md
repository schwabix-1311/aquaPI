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
- `/wiring`'s "receives" dropdown doesn't filter by data-type
  compatibility (e.g. History could be offered a STRING source).
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

- Real `log.brief`/`log.verbose` logging methods, instead of today's
  `log.brief = log.warning` hack (`logging.WARNING` reused as a
  `BRIEF` level, present in `msg_bus.py`, `alert_nodes.py`,
  `aux_nodes.py`) - `log.verbose()` as a
  `functools.partialmethod(log.log, loglevel.INFO-1, ...)` was one
  proposed real fix.
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
- Use `node.group` to allow multiple dashboards - might need
  `node.group` to change from a single string to a set of group names,
  since a node could then belong to more than one dashboard.
- Move the app name ("aquaPi") into a global config value, to allow
  installations under a different name (working title "poolPi").
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

<!-- add items below as they come up -->
