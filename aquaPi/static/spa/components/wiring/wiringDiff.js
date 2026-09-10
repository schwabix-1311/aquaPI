// Pure diff of the /wiring draft against the baseline it was seeded
// from. No Vue, no store - runs under node:test (tests/js/wiringDiff.test.js).
//
//   wiringDiff(baseline, working, nodeTypes)
//     -> {creates, updates, deletes, hasChanges}
//
// in exactly the shape POST /api/config/apply expects:
//   creates: [{temp_id, type, name, receives, fields, group, pos_x, pos_y}]
//   updates: [{id, ...only the keys that actually changed}]
//   deletes: [id, ...]
//
// `baseline` / `working` are {id: node} maps of plain node objects (as
// the REST API returns them). A working id absent from baseline is a
// create; a baseline id absent from working is a delete; a surviving id
// yields an update entry carrying ONLY the fields whose value differs.
//
// Deriving the diff structurally (instead of tracking _new/_dirty/
// _deleted flags by hand and re-deciding at save time) removes a whole
// class of bug: e.g. a node the auto-layout only nudged in pos never
// carries a stale `receives` into the payload, and an Alert - whose
// `receives` is 'none' in the schema and edited through its own endpoint
// - never has `receives` emitted for it at all.

function schemaFieldKeys(node, nodeTypes) {
	const schema = nodeTypes && nodeTypes[node.type]
	return (schema && schema.fields || []).map(f => f.key)
}

function fieldsOf(node, nodeTypes) {
	const fields = {}
	schemaFieldKeys(node, nodeTypes).forEach(key => {
		if (node[key] !== undefined) {
			fields[key] = node[key]
		}
	})
	return fields
}

const scalarOf = (key, node) => key === 'group' ? (node[key] || '') : (node[key] || 0)

export function wiringDiff(baseline, working, nodeTypes) {
	const creates = []
	const updates = []
	const deletes = []
	if (!baseline || !working) {
		return {creates, updates, deletes, hasChanges: false}
	}

	for (const id of Object.keys(baseline)) {
		if (!(id in working)) {
			deletes.push(id)
		}
	}

	for (const [id, node] of Object.entries(working)) {
		const base = baseline[id]

		if (!base) {
			creates.push({
				temp_id: node._tempId || id,
				type: node.type,
				name: node.name,
				receives: node.receives || [],
				fields: fieldsOf(node, nodeTypes),
				group: node.group || '',
				pos_x: node.pos_x || 0,
				pos_y: node.pos_y || 0,
			})
			continue
		}

		const upd = {id}
		let changed = false

		for (const key of ['group', 'pos_x', 'pos_y']) {
			if (scalarOf(key, node) !== scalarOf(key, base)) {
				upd[key] = scalarOf(key, node)
				changed = true
			}
		}

		// `receives` only for types that actually accept it - never for an
		// Alert (schema 'none'), whose receives is derived from conditions
		const schema = nodeTypes && nodeTypes[node.type]
		if (schema && schema.receives !== 'none') {
			const rNow = node.receives || []
			const rBase = base.receives || []
			if (JSON.stringify(rNow) !== JSON.stringify(rBase)) {
				upd.receives = rNow
				changed = true
			}
		}

		const fNow = fieldsOf(node, nodeTypes)
		if (JSON.stringify(fNow) !== JSON.stringify(fieldsOf(base, nodeTypes))) {
			upd.fields = fNow
			changed = true
		}

		if (changed) {
			updates.push(upd)
		}
	}

	return {
		creates, updates, deletes,
		hasChanges: !!(creates.length || updates.length || deletes.length),
	}
}

// vim: set noet ts=4 sw=4:
