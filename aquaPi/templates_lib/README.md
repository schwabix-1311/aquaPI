# Predefined templates

Each `*.json` file here is a **predefined node-combination template** —
a small, portable sub-graph (e.g. "temperature control with heater") that
the user can drop into their wiring from the Wiring page.

These are shipped and read-only: they show up with `source: "predefined"`
in `GET /api/templates/` and cannot be deleted through the API.

## File format

```json
{
  "id": "temp-heater",
  "i18n": {
    "de": { "name": "Temperatur (Heizstab)", "descr": "Sensor → Regler → Relais",
            "nodes": { "sensor": "Wasser", "ctrl": "Heizleistung", "out": "Heizstab" } },
    "en": { "name": "Temperature (heater)",  "descr": "sensor → controller → relay",
            "nodes": { "sensor": "Water", "ctrl": "Heat output", "out": "Heater" } }
  },
  "data": { "nodes": [ { "id": "sensor", ... }, { "id": "ctrl", ... }, ... ] }
}
```

- **`id`** — stable, language-independent. It's the API path segment
  (`/api/templates/<id>`) and the merge key vs. a user template. Also the
  file name (any unique `*.json` name works, but matching `id` is tidiest).
- **`i18n`** — per-language `name` / `descr` and a `nodes` map from each
  `data.nodes[].id` to that node's localised display name. `list_templates`
  / `get_template` fold in the caller's `?lang=` (fallback: `de` → `en` →
  whatever's present). At instantiate time the localised name becomes the
  new node's name (and, via the usual slug, its id).
- **`data`** — exactly what `db.capture_node_template()` produces. The
  `state.name` values in here are only a fallback for languages the `i18n`
  block doesn't cover.

A plain user template has no `id` / `i18n`, just `{ "name", "descr",
"data" }`; its `id` is its `name` and it's shown verbatim in every
language.

## Adding one

Build the block set in the running app, save it as a template (it lands
in `<instance>/templates/` as `{name, descr, data}`), check it, then
promote it: add an `id` + an `i18n` block, and

```
git mv instance/templates/<file>.json aquaPi/templates_lib/<id>.json
git commit
```

A user template with the same `id` shadows the predefined one, so a user
can still override it locally; deleting their copy brings this one back.
