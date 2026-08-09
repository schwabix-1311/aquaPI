---
sessionId: session-260802-063658-1699
---

# ⚠ Breaking change heads-up (not a task plan - informational)

Written by Claude Code (dev_m) for Junie/thk's attention, merged into
`dev_thk` via commit `a2a3b15`. Source commit: `05a47f5` "Replace
REAL_CONFIG/TEST_BUS source toggles with topology-name-driven config;
fix -r".

## What changed

`machineroom/__init__.py`'s `create_default_nodes()` used to pick the
default node set (only relevant when bootstrapping a genuinely empty
topology) via two hardcoded booleans, `TEST_BUS`/`REAL_CONFIG`, that
had to be manually kept out of every commit. Replaced with a
topology-name-driven selection instead:

- Priority: `-t NAME` (one-off) > `instance/config.json`'s
  `"DEFAULT_CONFIG"` key (persistent, gitignored) > `'topo'` (hardcoded
  fallback).
- `'topo'` (the new default) -> the real/production node set.
- `'test_bus'` -> the minimal test bus.
- Anything else (e.g. `'dev'`) -> the existing dev/simulated node set
  (`TEST_PH`/`SIM_LIGHT`/`SIM_TEMP`/`COMPLEX_TEMP`, unchanged).
- Each named config now gets its own `instance/<name>.sqlite` - real
  and dev topologies coexist, switching no longer requires `-r`.

## Why this is breaking for you specifically

The **repo-committed default before this change was `REAL_CONFIG =
False`** - meaning a fresh bootstrap (no `instance/topo.sqlite` yet)
fell through to the dev/simulated node set by default. **After this
change, the default is `'topo'` = the real/production config.** If you
ever bootstrap a fresh topology without an explicit `-t` or an
`instance/config.json` override (fresh clone, deleted
`instance/topo.sqlite`, or a `-r` reset - see below), you'll now get
the real production node set (real GPIO/ADC/PWM port assignments)
instead of the dev/simulated one you may be expecting.

**If you want the old default behavior back**: add `"DEFAULT_CONFIG":
"dev"` to your own `instance/config.json` (gitignored, machine-local -
see `machineroom/__init__.py`'s updated comments), or pass `-t dev`
per invocation.

## Second, separate gotcha: `-r` used to be a silent no-op

`dbg`/`run`'s `-r` flag had been broken since the topology's
pickle->SQLite migration - it only ever deleted the long-gone
`instance/<name>.pickle`, never the actual `instance/<name>.sqlite`.
**Resetting had no real effect.** This is now fixed: `-r` deletes both
files and genuinely resets the topology. If you've been using `-r`
out of habit assuming it doesn't do much, be aware it now actually
wipes the selected topology's database.
