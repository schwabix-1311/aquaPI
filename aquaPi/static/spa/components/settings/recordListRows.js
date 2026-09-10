// Pure row <-> value helpers for the SettingRecordList widget (kept
// import-free so they - and their node:test unit tests - never pull in
// the Vue components).

export function subFieldsOf(item) {
	return (item && item.attrs && item.attrs.recordSchema) || []
}

let _rowKeySeq = 0
function freshKey() {
	_rowKeySeq += 1
	return 'rl' + _rowKeySeq
}

export function emptyRow(subFields) {
	const row = {_key: freshKey()}
	subFields.forEach(sf => { row[sf.key] = sf.value })
	return row
}

export function rowsFromValue(value, subFields) {
	return (value || []).map(rec => {
		const row = {_key: freshKey()}
		subFields.forEach(sf => {
			row[sf.key] = rec && rec[sf.key] !== undefined ? rec[sf.key] : sf.value
		})
		return row
	})
}

// rows -> the wire shape: drop _key, coerce numbers (a blank stays blank
// so the server can reject a required field clearly), and emit keys
// alphabetically - the REST API's own JSON encoder sorts keys, so this
// keeps a round-tripped value byte-identical (no phantom "dirty" in the
// /wiring diff, no needless re-seed in the /parameters widget).
export function stripRows(rows, subFields) {
	const byKey = {}
	subFields.forEach(sf => { byKey[sf.key] = sf })
	const keys = subFields.map(sf => sf.key).sort()
	return (rows || []).map(row => {
		const rec = {}
		keys.forEach(k => {
			let v = row[k]
			if ((byKey[k].attrs || {}).type === 'number'
				&& v !== '' && v !== null && v !== undefined) {
				v = Number(v)
			}
			rec[k] = v
		})
		return rec
	})
}

// which live-node filter applies to a node-ref sub-field in this row -
// a per-class override (nodeFilterByClass) wins over the plain nodeFilter
// (the per-class map is unused today, room for a future backend refinement).
export function nodeFilterFor(subField, row) {
	const a = subField.attrs || {}
	return (a.nodeFilterByClass && row && a.nodeFilterByClass[row.class])
		|| a.nodeFilter || null
}

// vim: set noet ts=4 sw=4:
