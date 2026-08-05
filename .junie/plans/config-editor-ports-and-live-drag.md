---
sessionId: session-260802-063658-1699
---

# Implementation Status: ✓ Done

Both delivery steps implemented and verified via a headless-browser (Puppeteer) session against the running app with a real admin login and the real 13-node/16-connection configuration:
- `ConfigNodeBox` now shows a small input-port marker (left edge, blue) and output-port marker (right edge, grey) based on `nodeTypes[node.type].receives` (`hasInput`/`hasOutput` computed props); verified 3 pure-sensor node types show only the output marker while all other (device/controller/history/alert) types show both markers.
- `AquapiConfig` (`components/config/index.js`) now tracks a `dragPositions` map fed by the existing per-mousemove `drag` event, and feeds a `nodesForConnections` computed (overlaying `dragPositions` onto the draft nodes) into `<config-connections>`; verified that dragging a connected node updates the affected connection `<path>`'s `d` attribute continuously during the drag (not just after mouseup), with no jump once the drag ends and `config/draftUpdateNode` still committing exactly as before. Only the client-side draft was touched during verification (never saved), so the real configuration was unaffected.

# Requirements

### Overview & Goals
A new, small correction round on top of the already-completed `/config` editor work (`.junie/plans/config-editor-adjustments-and-fixes.md`, Round 8 of `.junie/plans/vue3-vuetify3-vuex4-migration.md`). The user asked for two further improvements:

1. **Clearer input/output sides on node cards**: not every node type actually has an input (pure sensors/endpoints never accept `receives`), so the connector's attachment side (left = input, right = output) should be made visually obvious directly on the card, not just implied by the connector's own geometry.
2. **Connections should follow a card while it's being dragged**, not just snap into place after the drag ends.

### Current Implementation (relevant findings)
- `components/config/comps.js`'s `ConfigConnections.edges` computed already **geometrically** attaches every edge's start point to the source card's right-middle edge and its end point to the target card's left-middle edge (`x1 = source.pos_x + NODE_BOX_WIDTH`, `x2 = target.pos_x`) - i.e. "output = right, input = left" is already true of the *lines*, but there is currently **no visual marker on the card itself** indicating this, which is why it doesn't feel "clear".
- Each node type's input capability is already modeled server-side and exposed via `GET /api/node-types/` as `schema.receives` (`'none'` for pure sensor/endpoint types like `AnalogInput`/`SwitchInput`/`ScheduleInput` in `aquaPi/db.py`'s `NODE_TYPE_SCHEMA`, `'single'`/`'multi'` for devices/controllers/history/alerts) - already fetched into the store as `config/nodeTypes` and used by `ConfigNodeDialog`/`connectTo()` in `components/config/index.js`, but **not currently passed down to `ConfigNodeBox`**, so the box has no way to know whether to show an input port.
- Dragging: `ConfigNodeBox.onDragStart` fires a `drag` event on every `mousemove` (`components/config/comps.js`, ~line 91), but `AquapiConfig.onDrag` in `components/config/index.js` (~line 279) is a literal no-op with the comment `// local-only while dragging, position is committed on drag-end`. Only `onDragEnd` dispatches `config/draftUpdateNode`, which is what makes `nodes`/`edges` update - this is the confirmed root cause of connections not following a card while it's being dragged.

### Scope
**In Scope**
- Adding a small visual input/output port marker to each node card, shown/hidden based on the node type's actual `receives` capability.
- Making `ConfigConnections`'s rendered paths track a dragged card's position live, during the drag, not just after it ends.

**Out of Scope**
- Any change to the connector's routing algorithm (elbow paths, already implemented in Round 8) beyond making it reactive to live drag positions.
- Any change to the actual connect/disconnect logic (`connectTo`/`onRemoveEdge`) or to the backend `receives` schema.

### Functional Requirements
- A node card whose type has `receives: 'none'` shows only an output port marker (right edge); all other node types show both an input port marker (left edge) and an output port marker (right edge).
- Hovering a port marker shows a short tooltip identifying it as input or output (localized).
- While dragging a node card that has one or more existing connections (as source and/or target), those connection lines visibly move together with the card in real time, not just once the mouse button is released.
- Releasing the drag still commits the final position via the existing `config/draftUpdateNode` flow, unchanged.


# Technical Design

### Key Decisions
- **Port visibility source of truth**: use the existing `nodeTypes[node.type].receives` schema (already fetched from the backend, already the single source of truth used elsewhere for connect-ability, e.g. `connectTo()`'s `schema.receives === 'none'` check) rather than inferring from `node.role`, since `receives` is the precise, already-correct signal and avoids duplicating logic.
- **Output port is always shown**: the schema has no explicit "can be a source" flag, and in practice every node type can be subscribed to by something else (even an output device's state could theoretically be read by e.g. an alert), so showing the output port unconditionally is the simplest correct behavior without inventing new backend metadata.
- **Live-drag connections via a local override map, not a store dispatch per mousemove**: introduce a `dragPositions` map in `AquapiConfig` fed directly by the existing per-mousemove `drag` event, and feed a derived `nodesForConnections` array (only used by `ConfigConnections`, not by `ConfigNodeBox` itself, which already tracks its own local position) into the connections renderer. This avoids dispatching a Vuex action (and marking the draft dirty) on every mousemove, keeping the existing "commit only on drag-end" semantics intact while still getting live visual feedback.

### Proposed Changes
1. `components/config/index.js`: pass `:node-types="nodeTypes"` to `config-node-box`; add `dragPositions: {}` to `data()`; implement `onDrag(payload)` to set `this.dragPositions[payload.node.id] = {x: payload.x, y: payload.y}` (using `Vue.set`-equivalent reactive assignment pattern already used elsewhere in the store, or plain assignment since Vue 3's reactivity handles new object keys via `reactive()`/`ref()` proxies - confirmed compatible with this file's existing Options-API `data()` pattern); add `nodesForConnections` computed that overlays `dragPositions` onto `this.nodes`; pass it to `config-connections`; in `onDragEnd`, delete the node's `dragPositions` entry after dispatching `draftUpdateNode`.
2. `components/config/comps.js` (`ConfigNodeBox`): add a `nodeTypes` prop; add `hasInput`/`hasOutput` computed; render two small absolutely-positioned `<div class="config-node-port ...">` (or inline SVG circles) at the box's left/right edge, vertical center; add `title` tooltips using new i18n keys.
3. `aquaPi/static/css/app.css`: add `.config-node-port` base style (small circle, subdued color) plus `--in`/`--out` variants positioned via `left: -Npx` / `right: -Npx` and `top: 50%; transform: translateY(-50%)`.
4. `i18n/locales/de.js`/`en.js`: add `pages.config.portIn`/`pages.config.portOut` keys.

### Risks
- The port markers are purely decorative (not interactive drag-handles for creating new connections) in this round - creating this affordance is a natural follow-up but explicitly out of scope here, to keep the change small and consistent with what was requested.
- Overlaying `dragPositions` on top of `nodes` for the connections renderer only (not for `ConfigNodeBox` itself, which already manages its own local drag position) must be done carefully to avoid a double-offset or a one-frame flicker at drag-end - verified via headless-browser inspection of the path `d` attribute during and immediately after a drag.


# Testing

### Validation Approach
Frontend-only change (no Python/backend touched), validated via the project's established headless-browser (Puppeteer) approach against the running app with a temporary/real admin login, consistent with all prior correction rounds.

### Key Scenarios
- Load `/config` with the real node configuration; confirm sensor/endpoint-type cards (`receives: none`) show only an output port marker, while device/controller/history/alert cards show both input and output markers.
- Drag a node card that has at least one incoming and one outgoing connection; sample the connection `<path>`'s `d` attribute at multiple points during the drag (not just before/after) and confirm it changes continuously to track the card's live position.
- Release the drag and confirm the final path position matches the committed `pos_x`/`pos_y`, with no visible jump, and that `config/draftUpdateNode` is still called exactly as before.

### Edge Cases
- A node with no connections at all: dragging it should not throw even though `dragPositions` has an entry with no matching edges.
- Rapid drag-then-immediate-drag-again on the same node: `dragPositions` entry must be correctly cleared/reset between drags.

### Test Changes
- Modified `.js` files checked with `node --input-type=module --check`; no backend code is touched, so no `pytest` run is needed for this change per the agreed testing protocol.


# Delivery Steps

###   Step 1: Add visible input/output port markers to node cards
Every ConfigNodeBox shows a small port marker on its left edge (input) and/or right edge (output), so the connector attachment side is visually obvious instead of only implied by the line's geometry.
- Pass `nodeTypes` down from `AquapiConfig` (`components/config/index.js`) to `config-node-box` so each box can look up its own type's `receives` schema.
- In `ConfigNodeBox` (`components/config/comps.js`), add a `hasInput` computed (`nodeTypes[node.type]?.receives !== 'none'`) and a `hasOutput` computed (always true for now, since every node type can be a pub/sub source); render a small circle/handle absolutely positioned at the vertical center of the left edge (only if `hasInput`) and the right edge (`hasOutput`), reusing the existing `NODE_BOX_HEIGHT` for centering.
- Add matching CSS classes in `aquaPi/static/css/app.css` (e.g. `.config-node-port`, `.config-node-port--in`, `.config-node-port--out`) with distinct colors consistent with the existing connection line/arrow styling, plus a `title`/tooltip (`$t('pages.config.portIn')`/`$t('pages.config.portOut')`) and matching new i18n keys in `de.js`/`en.js`.
- Verify via headless browser that input-only node types (e.g. AnalogInput/SwitchInput/ScheduleInput, `receives: none`) show no input port, while device/controller/history/alert node types show both ports at the correct card edges.

###   Step 2: Make connection lines follow a card in real time while it is being dragged
Dragging a node card visibly drags its connected lines along with it instead of only updating them after the mouse button is released.
- In `components/config/index.js`, add a `dragPositions` reactive object (nodeId -> {x, y}); `onDrag(payload)` (currently a no-op) sets `this.dragPositions[payload.node.id] = {x: payload.x, y: payload.y}` on every mousemove tick emitted by `ConfigNodeBox`.
- Add a `nodesForConnections` computed that maps `this.nodes`, overriding `pos_x`/`pos_y` with any matching entry in `dragPositions`, and pass it to `<config-connections :nodes="nodesForConnections">` instead of the raw `nodes` prop.
- `onDragEnd(payload)` clears the corresponding `dragPositions[payload.node.id]` entry after dispatching the existing `config/draftUpdateNode` action, so the override is removed once the committed store position takes over (avoiding a visual jump).
- Verify via headless browser: drag a connected node card and confirm the SVG path's `d` attribute updates continuously during the mouse-move sequence (not just after mouseup), with no jump or lag once the drag ends, and that unrelated nodes/edges are unaffected.