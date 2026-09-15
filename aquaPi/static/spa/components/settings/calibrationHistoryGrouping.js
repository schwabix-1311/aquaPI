// Pure grouping helper for CalibrationHistory: one calibration event
// (applying a 2-point calibration, or editing offset/factor by hand)
// writes one calibration_log row PER CHANGED FIELD, a few milliseconds
// apart (see api.py's api_set_node_settings and db.py's
// apply_config_diff, both iterate a {key: value} dict and log each
// key that's offset/factor). Group rows back into one entry per event
// so the history reads "<date>: Faktor a->b, Offset c->d" instead of
// two separate lines with the same timestamp. Kept import-free so it -
// and its node:test unit tests - never pull in the Vue components.

export function groupCalibrationLog(entries) {
	const order = []
	const byKey = new Map()
	for (const entry of entries || []) {
		// truncate to whole seconds (ISO 'YYYY-MM-DDTHH:MM:SS...') - the
		// two writes of one event land within milliseconds of each other,
		// well under a second apart
		const key = entry.ts.slice(0, 19)
		if (!byKey.has(key)) {
			const group = {ts: entry.ts, offset: null, factor: null}
			byKey.set(key, group)
			order.push(group)
		}
		byKey.get(key)[entry.field] = {old: entry.old_value, new: entry.new_value}
	}
	return order
}
