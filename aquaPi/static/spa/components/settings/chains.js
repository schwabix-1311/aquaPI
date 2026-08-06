// Shared receives-chain grouping logic for the /settings page, used by
// both index.js (root-finding/grouping) and comps.js (Eingänge/Ausgänge
// rendering) - kept in one place so the two don't drift out of sync.
//
// A "root" is either a node nobody-else's `receives` points at and whose
// own `receives` is empty (the origin of a potential chain), or a
// HISTORY/ALERTS node unconditionally - those always get their own
// dedicated card, never nested inside whatever they're recording/watching.

function isHistOrAlert(node) {
	return node.role === 'HISTORY' || node.role === 'ALERTS'
}

function isRoot(node) {
	if (isHistOrAlert(node)) {
		return true
	}
	return (node.receives || []).every(id => id === '*')
}

// full downstream walk from `node`, excluding HISTORY/ALERTS (they're
// always their own separate root instead of being nested here).
// ancestorIds guards against a receives cycle.
function descendants(node, allNodes, ancestorIds) {
	ancestorIds = ancestorIds || [node.id]
	return Object.values(allNodes)
		.filter(candidate => !isHistOrAlert(candidate)
			&& !ancestorIds.includes(candidate.id)
			&& (candidate.receives || []).includes(node.id))
		.map(candidate => ({
			node: candidate,
			children: descendants(candidate, allNodes, [...ancestorIds, candidate.id]),
		}))
}

// flattens a {node, children} tree (as produced by descendants()/ancestors())
// into a single ordered list, depth-first
function flattenEntries(entries) {
	return entries.flatMap(entry => [entry.node, ...flattenEntries(entry.children)])
}

function flatten(node, allNodes) {
	// descendants() already threads the ancestor-guard through its own
	// recursion and returns the complete tree in one call - flatten just
	// walks that already-built, already-guarded tree. (Calling descendants()
	// again per node here, with a fresh guard each time, previously caused
	// infinite recursion on a two-node receives cycle.)
	return [node, ...flattenEntries(descendants(node, allNodes))]
}

// the CTRL node within this root's own chain, if any, else the root itself
function chainAnchor(root, allNodes) {
	if (isHistOrAlert(root)) {
		return root
	}
	return flatten(root, allNodes).find(n => n.role === 'CTRL') || root
}

// the given node's own upstream ancestry, walking `receives` backward.
// ancestorIds guards against a receives cycle.
function ancestors(node, allNodes, ancestorIds) {
	ancestorIds = ancestorIds || [node.id]
	return (node.receives || [])
		.filter(id => id !== '*' && !ancestorIds.includes(id))
		.map(id => allNodes[id])
		.filter(Boolean)
		.map(parent => ({
			node: parent,
			children: ancestors(parent, allNodes, [...ancestorIds, parent.id]),
		}))
}

export {isHistOrAlert, isRoot, descendants, flatten, flattenEntries, chainAnchor, ancestors}

// vim: set noet ts=4 sw=4:
