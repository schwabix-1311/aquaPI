---
generatedBy: Claude Code (dev_thk)
date: 2026-08-06
---

# Implementation Status: ✓ Done (Steps 1-4), 🗣️ Proposed for discussion (Step 5)

`Setting` (`aquaPi/machineroom/msg_bus.py`) now supports `type='select'`/`'multiselect'`
with an `options: list[str]` choice list, plus an `optional: bool` flag (fields are
required by default). Applied end-to-end to `/settings`'s `port` fields, which used to
be a freeform text box the user had to type an exact `IoRegistry` port name into, with
no validation and no visibility into what's actually free - it's now a dropdown of
currently-unused ports of the right kind (`Bin`/`Bout`/`Ain`/`Aout`), always including
the node's own currently-assigned port. Verified: full `pytest` suite (279/279) plus a
standalone script exercising `get_settings()`/`_validate_and_cast()` directly for
`SwitchInput`/`AnalogInput`/`SwitchDevice`/`SlowPwmDevice`/`AnalogDevice` (see Testing).

Step 5 (reusing this in `/config`'s node-creation dialog, and generalizing beyond ports)
is written up below but **not implemented** - it's here specifically so it can be
discussed before deciding whether to build it.

# Requirements

### Overview & Goals
Every `IoRegistry`-backed node (`InputNode`/`DeviceNode` subclasses) exposed its `port`
as a plain `'text'` `Setting` on `/settings` - the user had to type an exact port-name
string (e.g. `"GPIO 12 out"`) with no validation and no visibility into what's actually
free or already claimed by another node. `IoRegistry.get_ports_by_function(funcs,
in_use=False)` (`driver/__init__.py`) already returns exactly this information but had
no caller anywhere in the app. Goal: give `Setting` a generic "pick one/several from a
list" capability and use it to fix `port`.

### Scope
**In Scope**
- A new `type='select'` (pick one) / `type='multiselect'` (pick several) on `Setting`,
  with a sibling `options: list[str]` field.
- A new `optional: bool` field on `Setting` (default `False` - **fields are required
  by default**, opt into optionality per-field rather than the reverse).
- Applying `type='select'` + live `IoRegistry` options to the `port` field on
  `SwitchInput`, `AnalogInput`, `SwitchDevice`, `SlowPwmDevice`, `AnalogDevice`.

**Out of Scope (this round)**
- `/config`'s `NODE_TYPE_SCHEMA` (`db.py`) - its `port` fields are still plain `'text'`.
  See Step 5.
- Alert-node notification "ports" (Email/Telegram) - they don't currently expose a
  `port` `Setting` at all, so there's no existing text field to fix.
- Anything beyond ports - `FilterCond` (`AlertNode`, not yet built) and a generic
  `BusNode.receives` editor are noted as *future* consumers of the same mechanism in
  Step 5, not built now.

### Functional Requirements
- A `port` field on any of the five node types above renders as a dropdown of
  currently-free ports of the right `PortFunc`, plus the node's own current port if it
  has one (even though `IoRegistry` marks that port "in use" by this same node).
- Submitting an empty or already-used port via `PUT /api/nodes/<id>/settings` is
  rejected (400) - `port` has no explicit `optional=True`, so it's implicitly required
  like every other `Setting` now is by default.
- `/config`'s existing node-creation/edit flow (`NODE_TYPE_SCHEMA`, `_validate_fields`)
  is **unaffected** - still accepts a blank `port` at creation time, exactly as before.


# Technical Design

### Key Decisions
- **`type='select'`/`'multiselect'` instead of `Setting.type` sometimes being a
  `list`**: keeps `type` a plain string discriminator everywhere it's already checked
  (`api.py`'s `_validate_and_cast`, `comps.js`'s `settingWidgetType()`), instead of
  every consumer needing an `isinstance(type, list)` branch.
- **`options: list[str]` is flat, not `{value, label}` pairs**: `IoRegistry` port names
  are already both the unique key and the human-readable label (e.g. `"GPIO 12 out"`),
  so no mapping is needed - `v-select` accepts plain string items directly.
- **Fields are required by default (`optional: bool`, not `required: bool`)**: an
  earlier draft added `required: bool = False`, i.e. *opt-in* to being required. In
  practice almost every real `Setting` (a port, a setpoint, a cron spec, ...) is
  conceptually mandatory - defaulting to "not required" and marking each individually
  would mean adding `required=True` to nearly every one of the ~25 existing
  `get_settings()` call sites. Flipped it: `optional: bool = False` - **required by
  default**, with the few genuinely-optional-with-sensible-defaults fields
  (`hysteresis`, `unit`, `p_fact`/`i_fact`/`d_fact`, ...) left as a later pass rather
  than guessed at now. `port` gets no override, so it's required like everything else -
  the dropdown's former `''` "no port" placeholder was removed since offering a choice
  that always fails validation is a dead end.
- **The wire attribute is also named `optional`, not translated to `required`**: keeps
  the Python dataclass field, the JSON `attrs.optional`, and the Vue widgets' check all
  using the same word, rather than a `Setting.optional` → JSON `attrs.required`
  translation that would read as two different concepts for the same flag.
- **`/config`'s own required/default handling (`NODE_TYPE_SCHEMA`, `db.py`) is left
  alone, deliberately**: the shared `_validate_and_cast()` now defaults to
  "required" too, which would have started rejecting `/config`'s existing
  `port: ''`-at-creation flow (relied on by `test_node_crud_api.py`) as a side effect.
  Its one call site (`_validate_fields`) now explicitly passes `voptional=True` to keep
  its prior behavior - `/config` already has its own, separate required/default
  handling per schema field (`field.get('required')`, checked only for *missing* keys,
  not submitted-but-blank ones), and that's intentionally not touched here (see Step 5
  on why: it's considered unreliable/prototype-stage right now).

### Proposed Changes (implemented)
1. `aquaPi/machineroom/msg_bus.py`: `Setting` gains `options: list[str] | None = None`
   and `optional: bool = False`.
2. `aquaPi/api.py`:
   - `_settings_entry_to_dict`: `attrs.options` / `attrs.optional` added (omitted when
     `None`/`False`, same convention as the existing `min`/`max`/`step`).
   - `_validate_and_cast(key, raw_value, vtype, vmin, vmax, voptions, voptional)`:
     new required-unless-optional check up front; new `'select'`/`'multiselect'`
     branches validating against `voptions`.
   - `_validate_fields` (the `/config` path): explicitly passes `voptional=True` to
     preserve its previous (unenforced) behavior - see Key Decisions.
3. `aquaPi/static/spa/components/settings/comps.js`: new `SettingSelect`/
   `SettingMultiSelect` components; a shared `requiredRule(item, t)` helper (skips the
   rule when `attrs.optional`) wired into `SettingNumber`/`SettingText`/`SettingSelect`/
   `SettingMultiSelect` as a client-side hint (server is still the source of truth);
   `settingWidgetType()` dispatches `'select'`/`'multiselect'` to the two new
   components. New `misc.dialog.valueRequired` i18n key (`de.js`/`en.js`).
4. `aquaPi/machineroom/{in_nodes,out_nodes}.py`: `InputNode`/`DeviceNode` gain a
   `_port_funcs: list[PortFunc]` class attribute (empty on the abstract base), set per
   concrete subclass by checking each driver's actual `PortFunc` (`grep PortFunc.
   aquaPi/driver/*.py`): `SwitchInput`→`Bin`, `AnalogInput`→`Ain`, `SwitchDevice`/
   `SlowPwmDevice`→`Bout` (both drive a boolean GPIO/relay, confirmed by reading their
   `write()`/`_pulse()` code - `SlowPwmDevice` looked at first glance like it might need
   `Aout`, since it's described as "analog output", but it actually bit-bangs a boolean
   pin), `AnalogDevice`→`Aout`. Their `get_settings()` now builds `port`'s `options`
   from `IoRegistry.get().get_ports_by_function(self._port_funcs, in_use=False)`, plus
   the node's own current port if truthy and not already in that free set.

### Risks
- A node's own port must always be included in `options` even though `IoRegistry`
  marks it "in use" (by itself) - handled, verified below.
- Concrete subclasses each needed the *correct* `PortFunc`, not just any plausible
  guess - verified by reading each class's actual driver-write call, not assumed from
  the docstring (caught `SlowPwmDevice` this way, see above).


# Testing

### Validation Approach
Full `pytest` suite (backend-only change) plus a standalone script (not a browser
session - avoided needing a live login) that imports the machineroom modules directly,
mirroring `tests/conftest.py`'s `io_registry` fixture setup (`create_io_registry()`).

### Key Scenarios (all passed)
- `SwitchInput`/`AnalogInput`/`SwitchDevice`/`SlowPwmDevice`/`AnalogDevice.get_settings()`
  each return a `port` `Setting` with `type='select'` and the right `PortFunc`-filtered
  `options`.
- A node's own currently-assigned port appears in its own `options` even though
  `IoRegistry` marks it used.
- A *different*, freshly-constructed node of the same port-function does **not** see
  an already-claimed port in its `options` (e.g. a second `SwitchDevice` doesn't see
  `"GPIO 12 out"` once a first one holds it).
- `_validate_and_cast('port', '', 'select', voptions=..., voptional=False)` raises
  (`port: value is required`); a real free port validates and returns correctly.
- `_settings_entry_to_dict` omits `attrs.optional` entirely when `False` (the common
  case), matching the existing `min`/`max`/`step`-omit-when-`None` convention.

### Test Suite
`venv/bin/python -m pytest tests/` - **279 passed**, run twice (once before, once after
the `required`→`optional` rename) to confirm the `/config` call-site fix
(`voptional=True`) actually prevents the regression it was written to prevent.


# Delivery Steps (for discussion: Step 5)

###   Step 5: Reuse `Setting` in `/config`, and beyond ports
Not started - written up for review before deciding to build it.

- **Reuse in `/config`**: `db.py` already documents (`db.py:96-98`) that
  `NODE_TYPE_SCHEMA` field dicts intentionally mirror `get_settings()`'s shape. Once
  `Setting` has `options`, `/config`'s own `port` fields (still `'text'` today, `db.py`
  lines 104/116/131/142/151) have the exact same problem `/settings`'s did. Formalizing
  the mirrored shape into one real type would need `api_node_types()` (currently just
  `jsonify`s a static module-level constant, built once at import time) to compute the
  `port` field's `options` live per-request from `IoRegistry`, instead of serving a
  frozen dict - a bigger change than it sounds, and the reason this is a separate,
  explicitly-not-yet-trusted step: **`/config`'s own required-field handling is
  currently prototype-quality** (e.g. it already tolerates/relies on a blank `port` at
  creation - see `test_node_crud_api.py`), so unifying it with `/settings`'s new
  required-by-default model needs its own careful pass, not a drive-by.
- **Beyond ports**: the mechanism (`type='select'`/`'multiselect'` + `options`) was
  deliberately kept generic (not `IoRegistry`-specific) so it can also serve:
  - `FilterCond` values on `AlertNode` (not yet built).
  - A generic `BusNode.receives` editor - `NodeReceivesEditor`
    (`comps.js`, today a bespoke `v-select` living outside the `Setting`/
    `settingWidgetType` dispatch, saving through a different endpoint,
    `configStore.updateNode` rather than the settings API) could eventually collapse
    into an ordinary `multiselect` `Setting` like any other field.
