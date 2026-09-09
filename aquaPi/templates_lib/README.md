# Predefined templates

Each `*.json` file here is a **predefined node-combination template** —
a small, portable sub-graph (e.g. "temperature control with heater") that
the user can drop into their wiring from the Wiring page.

These are shipped and read-only: they show up with `source: "predefined"`
in `GET /api/templates/` and cannot be deleted through the API.

## File format

```json
{
  "name": "Temperatur (Heizstab)",
  "descr": "Sensor -> Schwellwertregler -> Relais",
  "data": { "nodes": [ ... ] }
}
```

`data` is exactly what `db.capture_node_template()` produces. The file
name only needs to be unique and end in `.json`; the real name is the
`name` field inside.

## Adding one

Build the block set in the running app, save it as a template (it lands
in `<instance>/templates/`), check it looks right, then promote it:

```
git mv instance/templates/<file>.json aquaPi/templates_lib/<file>.json
git commit
```

A user template of the same `name` shadows the predefined one, so a user
can still override it locally; deleting their copy brings this one back.
