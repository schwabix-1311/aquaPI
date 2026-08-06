---
sessionId: session-260802-063658-1699
---

# Requirements

### Overview & Goals
This is **Step 5** of the already-implemented plan `.junie/plans/settings-select-optional-fields.md` (Steps 1-4 are ✓ Done and gave `Setting` a generic `type='select'`/`'multiselect'` + `options: list[str]` + `optional: bool` capability, applied to `/settings`'s `port` fields). Step 5 was written up for discussion but never built; the user has now approved doing **both** parts described there:

1. **Reuse in `/config`**: apply the same `select`-with-live-`IoRegistry`-`options` treatment to `/config`'s own `port` fields (`NODE_TYPE_SCHEMA` in `db.py`, currently still `type: 'text'`), so creating/editing `AnalogInput`/`SwitchInput`/`AnalogDevice`/`SlowPwmDevice`/`SwitchDevice` nodes on `/config` also gets a dropdown of free ports instead of a freeform text box.
2. **Beyond ports**: reduce the amount of bespoke, `Setting`-mechanism-external UI. The concrete existing candidate for this (per the plan doc) is `components/settings/comps.js`'s `NodeReceivesEditor` - a hand-rolled `<v-select multiple chips>` for History/Alert nodes' `receives`, which duplicates the look/behavior that `SettingMultiSelect` (built in Step 3) already provides for every other multiselect field.

### Investigation Findings (why this needs care, not a drive-by)
- `_validate_and_cast()`'s `'select'`/`'multiselect'` branches currently check `raw_value` against `voptions` **unconditionally**, even when `voptional=True`. `/config`'s shared validator `_validate_fields()` (`api.py`) always calls `_validate_and_cast(..., voptional=True)` for *submitted* values (its own required/default handling only looks at *missing* keys - see `db.py:96-98`'s documented mirroring). If `NODE_TYPE_SCHEMA`'s port fields are switched to `type: 'select'` as-is, submitting `port: ''` at node creation (relied on today, e.g. by `test_node_crud_api.py`) would newly fail with `"'' is not a valid choice"`, since `''` is never itself a member of the live `options` list. **This must be fixed first**, not worked around in the frontend.
- `api_node_types()` (`api.py`) currently just `jsonify(db.NODE_TYPE_SCHEMA)` - a frozen, module-level dict built once at import time. To show *live* free-port options (which change as nodes are created/ports get claimed), it needs to compute `port` fields' `options` per-request, reusing the exact same `_port_funcs` → `IoRegistry.get().get_ports_by_function(...)` mechanism Steps 1-4 already built for `get_settings()` on the five concrete node classes.
- `receives` editing (`PUT /api/nodes/<id>`, `api_update_node`) has real validation beyond a plain options-membership check: cardinality (`'single'`→max 1, `'none'`→must be empty), existence of every target id, and **cycle detection** (`db.would_create_cycle`). None of this lives in the generic `Setting`/`_validate_and_cast` machinery, and moving it there wholesale is exactly the kind of "drive-by" the original plan doc warns against. This plan keeps that validation exactly where it is (`api_update_node`) and only unifies the **rendering** of `NodeReceivesEditor`, not its save path or backend validation.

### Scope
**In Scope**
- Backend: relax `_validate_and_cast`'s `select`/`multiselect` branches so an empty value only skips the options check when `voptional=True` (i.e. the `/config` semantics), without weakening `/settings`'s existing required-by-default behavior (which already rejects blank before reaching that check).
- Backend: `api_node_types()` computes each of the five node types' `port` field `options` live from `IoRegistry`, mirroring `get_settings()`'s per-node logic; `NODE_TYPE_SCHEMA`'s `port` fields change `type` from `'text'` to `'select'`.
- Frontend: `ConfigNodeDialog` (`components/config/comps.js`) gains `'select'`/`'multiselect'` rendering branches in its per-field loop (currently only `checkbox`/`number`/text-fallback), so the node create/edit dialog on `/config` shows the new dropdown.
- Frontend: `NodeReceivesEditor` (`components/settings/comps.js`) is re-rendered using the existing `SettingMultiSelect` component (built in Step 3) instead of its own bespoke `<v-select multiple chips>` markup, for visual/behavioral consistency (chips, required-hint styling) - its save mechanism (`configStore.updateNode` → `PUT /api/nodes/<id>`) and all of `api_update_node`'s receives validation (cardinality/existence/cycle) are **left untouched**.

**Out of Scope**
- Moving `receives` validation/persistence onto the `/settings` API (`PUT /api/nodes/<id>/settings`) - it stays on `PUT /api/nodes/<id>` since that's where the cycle/cardinality checks already correctly live.
- `FilterCond` values on `AlertNode` - these don't exist as an editable UI at all today (no `conditions` editor has ever been built), so there is nothing concrete to "reuse" the mechanism for yet; building a conditions editor from scratch is a separate, much larger feature, not part of this reuse-focused step.
- Any other `/config` field beyond `port` (e.g. `setpoint`, `cronspec`) - none of those have a bounded choice list today.

### Functional Requirements
- Creating or editing an `AnalogInput`/`SwitchInput`/`AnalogDevice`/`SlowPwmDevice`/`SwitchDevice` node on `/config` shows its `port` field as a dropdown of currently-free ports of the right kind (plus, when editing, the node's own current port), exactly mirroring `/settings`'s existing behavior.
- `/config`'s existing behavior of allowing a **blank** `port` at node creation, and of validating a **non-blank** port strictly against the free-port list, is preserved - no existing `/config` test's assumptions change.
- The History/Alert nodes' "Inputs" (`receives`) editor on `/settings` renders through the same `SettingMultiSelect` component used everywhere else, with the same required-field hint styling, while still saving via the existing `configStore.updateNode` call and still being rejected server-side for cycles/cardinality/unknown ids exactly as before.


# Technical Design

### Current Implementation (relevant)
- `aquaPi/api.py`'s `_validate_and_cast()` (lines ~298-337): the `voptional` early-exit only guards the *required* check (`raw_value in (None, '', [])`); the `'select'`/`'multiselect'` branches below it always check `voptions` membership regardless of `voptional`.
- `aquaPi/api.py`'s `_validate_fields()` (lines ~398-427) always passes `voptional=True` into `_validate_and_cast` for *submitted* values - its own required/default handling only fires for **missing** keys (`elif require_all: ... field.get('required')`).
- `aquaPi/api.py`'s `api_node_types()` (lines ~430-439): `return jsonify(db.NODE_TYPE_SCHEMA)` - a static dict.
- `aquaPi/db.py`'s `NODE_TYPE_SCHEMA` (lines ~100-154+): `port` fields are `{'key': 'port', 'label': '...', 'type': 'text', 'default': ''}` for the five relevant types.
- `aquaPi/machineroom/{in_nodes,out_nodes}.py`: each of the five concrete classes already has a `_port_funcs: list[PortFunc]` class attribute (from Steps 1-4) and already computes its own live `options` inside `get_settings()` via `IoRegistry.get().get_ports_by_function(self._port_funcs, in_use=False)` plus its own current port.
- `components/config/comps.js`'s `ConfigNodeDialog` (lines ~255-276): per-field `v-for` renders `v-switch` for `checkbox`, `v-text-field type=number` for `number`, else a plain `v-text-field` - no `select`/`multiselect` branch exists yet.
- `components/settings/comps.js`'s `NodeReceivesEditor` (lines ~453-512): bespoke `<v-select v-model="selected" :items="receivesItems" multiple chips>`, its own `saving`/`selected` state, and its own `configStore.updateNode({nodeId, changes: {receives: value}})` call with toast handling - functionally solid, just visually/structurally divergent from `SettingMultiSelect`.
- `components/settings/comps.js`'s `SettingMultiSelect` (built in Step 3, alongside `SettingSelect`): renders a `v-select multiple chips` bound to `entry.value`/`entry.attrs.options`, wired through the shared `requiredRule(item, t)` helper and the standard `/settings` save flow.

### Key Decisions
- **Fix the `select`/`multiselect` options-check to only apply to non-empty values, globally in `_validate_and_cast`**, rather than adding a `/config`-specific bypass: since `/settings` already rejects blank values via the earlier required check (`voptional=False` there), this change is a no-op for `/settings` and exactly fixes `/config`'s (`voptional=True`) blank-value case - one small, well-understood change instead of forking validation logic per caller.
- **`api_node_types()` becomes request-computed for `port` fields only**, not a wholesale rewrite of `NODE_TYPE_SCHEMA` into a function: a small helper (e.g. `db.get_node_type_schema()`) deep-copies the static schema and, for each of the five known port-bearing types, overwrites that field's `options` using the same `_port_funcs`/`get_ports_by_function` call already used by `get_settings()` - reusing the exact class attribute Steps 1-4 introduced, not inventing a second mapping.
- **`NodeReceivesEditor` keeps its own component identity and save path**, but delegates rendering to `SettingMultiSelect` by constructing a small pseudo-`Setting`-shaped object (`{key: 'receives', label: $t(...), value: selected, attrs: {options: receivesItems}}`) and listening for its `update`/`save` event to call the existing `configStore.updateNode(...)` - this keeps `api_update_node`'s cycle/cardinality/existence validation as the sole source of truth for `receives`, while eliminating the duplicated visual markup.

### Proposed Changes
1. `aquaPi/api.py`, `_validate_and_cast()`: change the `'select'` branch's options check to `if raw_value and voptions is not None and raw_value not in voptions:`, and the `'multiselect'` branch's to only check membership for a non-empty list (an empty list already passes trivially via `all(...)` over zero items, so only the `'select'` branch needs the literal guard).
2. `aquaPi/db.py`: add `get_node_type_schema() -> dict` that deep-copies `NODE_TYPE_SCHEMA` and, for each of the 5 node classes with a `_port_funcs` attribute, replaces that type's `port` field with `{**field, 'type': 'select', 'options': [...]}` computed via `IoRegistry.get().get_ports_by_function(cls._port_funcs, in_use=False)`; change the 5 `NODE_TYPE_SCHEMA` port field literal `'type': 'text'` entries to `'type': 'select'` (options is only ever added dynamically, so the static dict itself has no `options` key - safe for any other, non-API consumer of the constant).
3. `aquaPi/api.py`, `api_node_types()`: return `jsonify(db.get_node_type_schema())` instead of the static dict.
4. `components/config/comps.js`, `ConfigNodeDialog`'s field-loop template: add `v-select` branches for `field.type === 'select'` (single) and `field.type === 'multiselect'` (with `multiple chips`), both reading `:items="field.options"`, ahead of the existing checkbox/number/fallback branches.
5. `components/settings/comps.js`, `NodeReceivesEditor`: replace the inline `<v-select>` markup with `<setting-multi-select :entry="pseudoSetting" @save="onSave">` (or the exact prop/event contract `SettingMultiSelect` already exposes, confirmed during implementation), keeping the component's existing `selected`/`saving` state and `configStore.updateNode` call as the actual persistence path.

### Risks
- The `_validate_and_cast` relaxation must not accidentally let a truly-required `/settings` `select` field accept `''` - mitigated by the fact that `/settings` `Setting`s default to `optional=False`, which already raises before reaching the relaxed check; verified explicitly in testing below.
- `get_node_type_schema()` deep-copies a dict containing only JSON-serializable primitives (str/bool/int/float/lists) today, so `copy.deepcopy` is safe and cheap per-request; if this ever needs to scale, it's a simple, isolated function to optimize later.
- Reworking `NodeReceivesEditor`'s template risks a regression in its currently-correct `watch: 'node.receives'` reset-on-external-change behavior - this is explicitly called out as a scenario to re-verify, not assumed to "just work" after the swap.


# Testing

### Validation Approach
Backend changes verified via targeted `pytest` runs (per the agreed "no full suite unless requested" protocol) plus a small standalone script exercising `_validate_and_cast`/`get_node_type_schema` directly, mirroring the approach already used for Steps 1-4. Frontend changes verified via the project's established headless-browser (Puppeteer) approach against the live app with a real admin login.

### Key Scenarios
- `_validate_and_cast('port', '', 'select', voptions=['GPIO 12 out'], voptional=True)` now returns `''` unchanged (no longer raises) - confirms the `/config`-blank-port-at-creation fix.
- `_validate_and_cast('port', '', 'select', voptions=[...], voptional=False)` still raises (the *required*-value check fires first, unchanged) - confirms `/settings` behavior is untouched.
- `_validate_and_cast('port', 'not-a-real-port', 'select', voptions=['GPIO 12 out'], voptional=True)` still raises "not a valid choice" - confirms non-empty invalid values are still rejected on `/config`.
- `db.get_node_type_schema()['SwitchDevice']['fields']` contains a `port` entry with `type='select'` and an `options` list reflecting currently-free `Bout` ports (using the existing `create_io_registry()` test fixture pattern from `tests/conftest.py`).
- On `/config`, creating a new `SwitchDevice` node shows a port dropdown with the free ports; selecting one and saving creates the node correctly; leaving it blank still creates the node with an empty port, exactly as before.
- On `/settings`, opening a History or Alert node's card still shows its "Inputs" multiselect (now backed by `SettingMultiSelect`'s rendering) with the correct currently-selected nodes, chips, and options; selecting a different set and saving still calls `PUT /api/nodes/<id>` and still gets rejected server-side if it would create a cycle.

### Edge Cases
- A node type with no free ports left of its kind still renders a (technically unselectable, but not crashing) dropdown; the node's own currently-assigned port is still present in `options` even when editing.
- `NodeReceivesEditor`'s external-change reset (`watch: 'node.receives'`) still correctly updates the displayed selection when another user/tab changes the node's wiring.
- Regression check: existing `tests/test_node_crud_api.py` (blank-port-at-creation reliance) and `tests/test_config_apply.py` (bulk apply path, which goes through the same `_validate_fields`/`db.apply_config_diff`) both still pass unchanged.

### Test Changes
- Targeted `pytest` run: `tests/test_node_crud_api.py`, `tests/test_config_apply.py`, plus any existing settings/select-related tests from Steps 1-4 (e.g. covering `SwitchDevice`/`AnalogDevice` port options) - no full-suite run unless explicitly requested, per the agreed protocol.
- All modified `.js` files checked with `node --input-type=module --check`.


# Delivery Steps

###   Step 1: Fix select/multiselect validation to preserve /config's blank-value semantics
The shared field validator no longer rejects a blank port value on /config's node-create/edit flow after its type changes to 'select', while /settings' required-by-default behavior stays exactly as it is today.
- In `aquaPi/api.py`'s `_validate_and_cast()`, change the `'select'` branch's options-membership check to only apply when `raw_value` is non-empty (`if raw_value and voptions is not None and raw_value not in voptions: ...`).
- Confirm the `'multiselect'` branch's existing `all(v in voptions for v in raw_value)` check is already a no-op for an empty list (no change needed there beyond verification).
- Verify with direct calls to `_validate_and_cast`: a blank value with `voptional=True` now passes through unchanged; a blank value with `voptional=False` still raises; a non-empty invalid value still raises in both cases.
- Run targeted regression: `tests/test_node_crud_api.py`, `tests/test_config_apply.py` (both currently rely on blank-port-at-creation working).

###   Step 2: Make /config's port fields live 'select' dropdowns backed by IoRegistry
The /config node-type metadata endpoint reports each port-bearing node type's port field as a 'select' with the currently-free ports as options, computed fresh per request.
- In `aquaPi/db.py`, add `get_node_type_schema()` that deep-copies `NODE_TYPE_SCHEMA` and, for `AnalogInput`/`SwitchInput`/`AnalogDevice`/`SlowPwmDevice`/`SwitchDevice`, replaces the `port` field's `type` with `'select'` and adds a live `options` list from `IoRegistry.get().get_ports_by_function(cls._port_funcs, in_use=False)`.
- Update `NODE_TYPE_SCHEMA`'s literal `port` field entries for those 5 types from `'type': 'text'` to `'type': 'select'`.
- Update `aquaPi/api.py`'s `api_node_types()` route to return `jsonify(db.get_node_type_schema())` instead of the static dict.
- Verify via a standalone script (mirroring `tests/conftest.py`'s `io_registry` fixture) that `get_node_type_schema()` returns the correct, currently-free `options` for each of the 5 types, and run the Stage 1 regression tests again to confirm nothing broke.

###   Step 3: Render /config's node dialog select/multiselect fields
Creating or editing a port-bearing node type on /config shows a dropdown of free ports instead of a freeform text field, with unchanged create/edit/save behavior.
- In `components/config/comps.js`'s `ConfigNodeDialog`, add `v-select` branches to the per-field template loop for `field.type === 'select'` (single, `:items="field.options"`) and `field.type === 'multiselect'` (with `multiple chips`), placed before the existing checkbox/number/text-fallback branches.
- Verify via headless browser with a real admin login: opening the "add node" dialog for `SwitchDevice`/`AnalogDevice`/etc. shows a port dropdown populated with free ports plus (when editing) the node's own current port; creating a node with a selected port, and separately with a blank port, both succeed exactly as before.

###   Step 4: Unify NodeReceivesEditor's rendering with the shared SettingMultiSelect widget
The 'Inputs' (receives) editor for History/Alert nodes on /settings visually and behaviorally matches every other multiselect field in the app, while its save path and all backend receives validation (cardinality/existence/cycle detection) remain exactly as they are today.
- In `components/settings/comps.js`, replace `NodeReceivesEditor`'s bespoke `<v-select multiple chips>` markup with the existing `SettingMultiSelect` component, fed a small pseudo-Setting object built from `receivesItems`/`selected`, keeping the component's own `saving` state and its existing `configStore.updateNode({nodeId, changes: {receives: value}})` call as the actual save path (unchanged, still going through `PUT /api/nodes/<id>` and `api_update_node`'s cycle/cardinality/existence checks).
- Preserve the existing `watch: 'node.receives'` reset-on-external-change behavior.
- Verify via headless browser with a real admin login: a History/Alert node's Inputs editor renders with the same chip-based multiselect look as other `SettingMultiSelect` fields, shows the correct current selection, saves successfully on a valid change, and is still rejected (with the existing error toast) when the change would create a wiring cycle.