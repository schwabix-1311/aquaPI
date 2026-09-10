// Draft-aware option list for the /wiring add/edit dialog's `port` select.
// Pure - unit-tested in tests/js/wiringPortOptions.test.js, no Vue/store.
//
// The node-type schema's `port` field carries two lists:
//   attrs.options  - ports the LIVE IoRegistry reports free right now
//   attrs.allPorts - every port of this node's function (free + in-use)
// Neither reflects unsaved draft edits, so a port a draft edit has just
// vacated (its owner moved to another pin) still looks "in use". Given
// the current draft node set and the baseline it was seeded from, the
// ports this node may pick are:
//   free-now  u  vacated-in-draft  u  this node's own current pick
//   minus  ports another draft node now holds
// everything intersected with allPorts, so a vacated port of a different
// function never leaks into an unrelated select.

export function draftPortOptions({
	free = [],
	allPorts = null,
	ownPort = '',
	draftNodes = [],
	baselineNodes = [],
	selfId = null,
}) {
	const universe = (allPorts && allPorts.length)
		? new Set(allPorts)
		: new Set([...free, ...(ownPort ? [ownPort] : [])])

	const heldByOthers = new Set()
	draftNodes.forEach(n => {
		if (n && n.id !== selfId && n.port) {
			heldByOthers.add(n.port)
		}
	})

	const out = new Set(free)
	baselineNodes.forEach(n => {
		// a baseline node's port that nobody in the draft still holds has
		// been freed by an as-yet-unsaved edit
		if (n && n.port && !heldByOthers.has(n.port)) {
			out.add(n.port)
		}
	})
	if (ownPort) {
		out.add(ownPort)
	}

	return [...out]
		.filter(p => universe.has(p) && (!heldByOthers.has(p) || p === ownPort))
		.sort((a, b) => a.localeCompare(b))
}

// vim: set noet ts=4 sw=4:
