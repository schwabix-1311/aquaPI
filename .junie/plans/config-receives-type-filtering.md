---
sessionId: session-260802-063658-1699
---

# Requirements

### Overview & Goals
The `/config` editor's receives picker (the combo box used when wiring
one node's input to another node's output, both when creating a new node
and when editing an existing one) currently lists **every other node in
the topology** as a candidate source, with no compatibility filtering at
all. This let a user wire a `History` node to receive from an `Alert`
node - `Alert.data_range` is `STRING` (its `.data` is a joined string of
triggered condition messages), but `History` blindly forwards whatever
it receives into a QuestDB `double` column with no validation. The moment
that wiring existed in the saved topology, the app crashed
deterministically on every subsequent start:
```
psycopg.DatabaseError: inconvertible value: `` [STRING -> DOUBLE]
```
(Alert re-posts its - initially empty - joined message on every bus
replay during `plugin()`, and `History.feed()` tries to insert that
string straight into a numeric column.)

Goal: filter the receives combo (and validate server-side, defense in
depth) so a source's `data_range` must be compatible with what the
target actually does with the data, instead of allowing any node to be
wired to any other node.

**Important framing correction from an earlier proposal**: the fix
should NOT hardcode "Alert" or block by node `ROLE`
(`HISTORY`/`ALERTS`). The real incompatibility is the *data type*, not
which kind of node produced it - if `Alert` were ever changed to post a
number (e.g. a count of currently-active conditions) instead of a joined
string, `History` could legitimately graph that. The rule must key on
`data_range`, so it stays correct if/when that changes.

### Current Implementation
- `ConfigNodeDialog.receivesItems` (`aquaPi/static/spa/components/config/comps.js`,
  ~line 363-368):
  ```js
  receivesItems: function() {
  	const selfId = this.editNode ? this.editNode.id : null
  	return this.nodes
  		.filter(n => n.id !== selfId)
  		.map(n => ({title: n.name + ' (' + n.type + ')', value: n.id, text: n.name + ' (' + n.type + ')'}))
  },
  ```
  Only excludes the node being edited itself - no data-type filtering.
- `data_range` is already serialized to the frontend per node
  (`state["data_range"] = self.data_range.name` in `BusNode.__getstate__`,
  `aquaPi/machineroom/msg_bus.py`) and already consumed client-side
  elsewhere, e.g. `dashboard/comps.js` branches on
  `node.data_range === 'ANALOG'`/`'BINARY'` - so this fix needs **no new
  backend computation** for the frontend half, unlike e.g. the `port`
  field's `options` (populated server-side in `get_node_type_schema()`
  from live `IoRegistry` state the client can't compute itself).
- `DataRange` enum (`aquaPi/machineroom/msg_bus.py:29-34`): `UNDEF`,
  `ANALOG`, `BINARY`, `PERCENT`, `PERC_3`, `STRING`. `STRING` is
  currently the *only* member `History` genuinely can't store (its
  QuestDB column is `value double`); `PERC_3` (a tuple of 3 percentages)
  is also not a plain scalar today, but out of scope here - not
  currently wired into any History in practice, and flattening it is a
  separate, bigger design question.
- Backend validation is cardinality/existence only, both in
  `aquaPi/db.py`'s `apply_config_diff` (the `/config` "Speichern"
  bulk-diff endpoint) and in `aquaPi/api.py`'s `api_create_node`/
  `api_update_node` (the dialog's per-node create/edit endpoints, also
  used by `NodeReceivesEditor` on `/settings` for Alert/History):
  - `db.py`'s `_check_receives_cardinality` (~line 369-374): only
    `none`/`single`/`multi` count checks.
  - `db.py`'s `resolve_ref` (~line 509-514): only checks the id exists.
  - `api.py`'s `api_create_node` (~line 499-501) and `api_update_node`
    (~line 566-568): identical `for rcv_id in receives: if not
    bus.get_node(rcv_id): ...` existence-only loops.
  All 4 spots are marked with a `TODO(config-receives-type-filtering)`
  comment pointing at this document.

### Scope
**In Scope**
- Filter `receivesItems` (frontend) to exclude `STRING`-`data_range`
  nodes from the receives combo, for both node creation and editing.
- Add the equivalent `data_range != STRING` check server-side, in both
  `db.py`'s `apply_config_diff` and `api.py`'s `api_create_node`/
  `api_update_node`, so the API rejects an incompatible wiring even if
  something other than the standard dialog posts it (defense in depth -
  this is what actually let the crash happen: the check needs to exist
  wherever `receives` is written, not just in the picker UI).

**Out of Scope**
- `PERC_3` handling - not currently a practical issue, flag but don't
  solve here.
- Any change to `Alert`'s own receives-editing flow
  (`NodeReceivesEditor` → `PUT /api/nodes/<id>`) - unaffected either way,
  since it edits what Alert *watches* (never `STRING`-typed sources
  today), not what watches Alert.
- Recovering/cleaning up any already-broken saved topology - a
  corrupted `instance/topo.sqlite` was already fixed out-of-band by
  deleting and recreating the default topology (`./dbg -r`).

### Functional Requirements
- Opening the "Add node" or "Edit node" dialog for any node type with a
  `receives` field no longer offers `STRING`-typed nodes (currently:
  `Alert`) as selectable sources.
- Attempting to save a `receives` wiring that includes a `STRING`-typed
  source - via `/api/config/apply` (the `/config` page's bulk save) or
  via `POST /api/nodes`/`PUT /api/nodes/<id>` directly - is rejected
  with a clear `400` error, not silently accepted.
- All currently-valid wiring (sensor → controller → device, sensor →
  History, sensor → Alert, etc.) continues to work exactly as before -
  only `STRING`-typed sources are newly excluded.


# Technical Design

### Key Decisions
- **Filter by `data_range`, not `ROLE` or node type.** See the framing
  correction above - this is the one decision this doc most needs to get
  right, since an earlier proposal in the same investigation got it
  wrong on the first pass.
- **No new backend "compute valid combo options" endpoint/schema field
  for this specific case.** Unlike `port`, `data_range` is *static,
  already-known information the frontend already has per node* - a
  plain client-side `.filter()` is sufficient and simplest. Don't
  over-engineer this into a server-computed-options mechanism just
  because that's the pattern used for `port` - use the right tool for
  what's actually a much simpler filtering need.
- **Defense in depth**: the frontend filter alone would have prevented
  the *picker* from offering Alert, but wouldn't have stopped a
  hand-crafted API call (or a future UI bug) from writing the same bad
  wiring - the backend check is what actually guarantees the invariant.

### Proposed Changes
1. `aquaPi/static/spa/components/config/comps.js` - `receivesItems`:
   add `.filter(n => n.data_range !== 'STRING')` alongside the existing
   self-exclusion filter.
2. `aquaPi/db.py` - `apply_config_diff`: build a
   `node_id -> data_range` lookup covering both remaining live nodes
   (`node.data_range.name` per node) and this diff's own new creates
   (right after `all_ids = remaining_ids | new_ids`, ~line 507). For
   statically-typed classes this is `NODE_FACTORY[type_name].data_range`;
   note `AvgAux`/`MinAux`/`MaxAux` (`MultiInAux` family) set `data_range`
   as an *instance* attribute derived from their own inputs at
   construction time (`aux_nodes.py:60`,
   `self.data_range = rcv.data_range`), not a class attribute - a
   brand-new one of these being created in the same diff needs its
   `data_range` resolved from its own (already-being-validated)
   `receives` entry instead of a class-level lookup. Add a new sibling
   check next to `_check_receives_cardinality` (~line 369) that raises
   `ConfigDiffError` if any resolved receives id's `data_range` is
   `STRING`; call it alongside `_check_receives_cardinality` in both the
   `prepared_creates` loop (~line 524-528) and the `updates_by_id` loop
   (~line 530-543).
3. `aquaPi/api.py` - add the same `data_range != STRING` check inline in
   both `for rcv_id in receives:` loops (`api_create_node` ~line
   499-501, `api_update_node` ~line 566-568), right where the existence
   check already happens.
4. Remove the 4 `TODO(config-receives-type-filtering)` comments left at
   each of these spots once the corresponding fix lands.

### Risks
- The `MultiInAux`-family instance-level `data_range` (point 2 above) is
  the one genuinely fiddly part - get the resolution order wrong (e.g.
  trying to read `data_range` off a brand-new `AvgAux` before its own
  receives have been validated/resolved) and the check could crash or
  silently no-op instead of validating correctly. Write a test for this
  specific case (a new `AvgAux`/`MinAux`/`MaxAux` created in the same
  diff as one of its own receives sources).
- Keep the frontend and backend rules in exact sync (`STRING` only, for
  now) - if one side ever needs to expand the blocked set (e.g. if
  `PERC_3` handling is tackled later), update both.


# Testing

### Validation Approach
Both a frontend (JS) and backend (Python/pytest) change - verify each
independently, then end-to-end.

### Key Scenarios
- `receivesItems` no longer includes any `STRING`-`data_range` node
  (currently: `Alert` instances) when opening the add/edit dialog for
  any other node type.
- `apply_config_diff` (`db.py`) rejects a diff wiring a `History` (or
  any other type) to receive from an `Alert`'s id, via `ConfigDiffError`,
  for both a `creates` entry and an `updates` entry.
- `api_create_node`/`api_update_node` (`api.py`) reject the same via
  `400 Bad Request` with a clear error message.
- All existing valid wiring in `tests/test_config_apply.py` continues to
  pass unchanged.
- New test: create an `AvgAux` in the same diff as one of the nodes it
  receives from (exercises the instance-level `data_range` resolution
  path).

### Test Changes
- `tests/test_config_apply.py`: add cases for the rejected-wiring
  scenarios above, following the file's existing cardinality/cycle-
  rejection test style.
- Full suite: `python -m pytest -q` should stay green (currently 278
  passed / 1 pre-existing unrelated failure in
  `test_step10_integration.py::test_fresh_start_without_any_legacy_files_creates_default_topology`,
  caused by a local dev-only `REAL_CONFIG` toggle, not this change).


# Delivery Steps

### Step 1: Frontend filter
`receivesItems` (`aquaPi/static/spa/components/config/comps.js`)
excludes `STRING`-`data_range` nodes from the receives combo. Remove the
`TODO(config-receives-type-filtering)` comment there once done.

### Step 2: Backend validation in `db.py`
`apply_config_diff` rejects any `receives` entry (create or update)
referencing a `STRING`-`data_range` node, via a new
`_check_receives_compatibility`-style check called alongside
`_check_receives_cardinality`. Handle the `MultiInAux`-family
instance-level `data_range` case explicitly (see Risks). Remove the
`TODO` comment above `_check_receives_cardinality`.

### Step 3: Backend validation in `api.py`
`api_create_node` and `api_update_node` reject the same via their
existing inline `for rcv_id in receives:` loops. Remove both `TODO`
comments.

### Step 4: Tests
Add the new rejection-path tests (and the `MultiInAux` same-diff case)
to `tests/test_config_apply.py`; confirm the full suite stays green.
