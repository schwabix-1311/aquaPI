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

function realParents(node, allNodes) {
	return (node.receives || [])
		.filter(id => id !== '*')
		.map(id => allNodes[id])
		.filter(Boolean)
}

// true if `root`'s whole descendant tree has no fan-out anywhere (every
// node has at most 1 real listener) - i.e. shapes 1[:1..]:0 / 1:1[:1...].
// Only checks fan-OUT (array length at each level of descendants()'s own
// tree) - fan-in (a node with 2+ real parents) does NOT disqualify a chain
// from being "plain": e.g. two sensors merging into one AvgAux that then
// continues through a single Ctrl to a single output is still one clean
// purpose, just with 2 inputs - the resulting card should still be titled
// by that Ctrl, not by an arbitrarily-chosen root.
function isPlainChain(root, allNodes) {
	function walk(entries) {
		if (entries.length > 1) {
			return false
		}
		return entries.every(entry => walk(entry.children))
	}
	return walk(descendants(root, allNodes))
}

// the node whose name becomes the CARD TITLE: chainAnchor()'s existing
// single-CTRL pick when the whole component is a plain, unbranching chain
// (unchanged from today) - otherwise the root itself always, since no
// single node can fairly represent 2+ independent branches. Both
// index.js's panel-grouping key and NodeSettingsCard's headline read this,
// not chainAnchor() directly, so they never disagree about which node "is"
// the chain.
function cardTitle(root, allNodes) {
	return isPlainChain(root, allNodes) ? chainAnchor(root, allNodes) : root
}

// the local anchor for ONE branch subtree (entry = {node, children}, e.g.
// one sibling at a fan-out point): first CTRL found walking just this
// branch's own subtree, else the branch's own first node.
// the local anchor for ONE branch subtree (entry = {node, children}, e.g.
// one sibling at a fan-out point): first CTRL found walking just this
// branch's own subtree, else the branch's own first node. Deliberately
// NOT the branch's sink even for a Ctrl-less branch: the badge marks
// which row is structurally the sibling of the other branch(es) at this
// same fan-out (matching its indentation level) - anchoring on a deeper
// node instead breaks that visual pairing, making the fan-out look
// lopsided (one branch has its badge right at the sibling level, the
// other's is one level further in, so the eye reads the deeper node as
// the "real" second branch instead).
function branchAnchor(entry) {
	const flat = [entry.node, ...flattenEntries(entry.children)]
	const ctrl = flat.find(n => n.role === 'CTRL')
	return {node: ctrl || entry.node, isCtrl: !!ctrl}
}

// Wraps descendants()'s raw tree, which re-walks a fan-in node's subtree
// under EVERY real parent reachable within this same walk (no cross-branch
// memory) - so a node's downstream subtree is only expanded the first time
// this walk reaches it (pre-order). Every later occurrence (a genuine
// fan-in merge, reached via a different real parent in the SAME tree)
// keeps its own row but is marked `merged: true` with children dropped,
// instead of re-rendering the same downstream subtree a second time.
function dedupeFanIn(entries, seen) {
	seen = seen || new Set()
	return entries.map(entry => {
		if (seen.has(entry.node.id)) {
			return {node: entry.node, merged: true, children: []}
		}
		seen.add(entry.node.id)
		return {node: entry.node, merged: false, children: dedupeFanIn(entry.children, seen)}
	})
}

// ancestors() walks BACKWARD from a node (its immediate parent first,
// increasingly distant ancestors nested deeper) - useful for discovering
// the full ancestor set, but the opposite of how a chain should actually
// be READ: root(s) first, flowing forward hop-by-hop toward the anchor,
// same reading direction as descendants(). Walks the same node set
// ancestors() would discover, but forward instead, for rendering. May
// contain genuine fan-in (a node reachable via 2+ real parents within
// this set, e.g. two sensors merging into one AvgAux upstream of a single
// Ctrl) - caller should dedupeFanIn() the result, same as descendants().
function ancestorsForward(anchor, allNodes) {
	const ancestorIds = new Set(flattenEntries(ancestors(anchor, allNodes)).map(n => n.id))

	function forwardChildren(node, visited) {
		if (visited.has(node.id)) {
			return []
		}
		visited = new Set([...visited, node.id])
		return Object.values(allNodes)
			.filter(candidate => candidate.id !== anchor.id
				&& ancestorIds.has(candidate.id)
				&& (candidate.receives || []).includes(node.id))
			.map(candidate => ({node: candidate, children: forwardChildren(candidate, visited)}))
	}

	// true roots of the ancestor set: every real parent of an ancestor-set
	// node is, by ancestors()'s own transitive closure, also in the set -
	// so "no real parents at all" and "no real parent within the set" are
	// equivalent here.
	return [...ancestorIds]
		.map(id => allNodes[id])
		.filter(node => realParents(node, allNodes).length === 0)
		.map(node => ({node, children: forwardChildren(node, new Set())}))
}

export {
	isHistOrAlert, isRoot, descendants, flatten, flattenEntries, chainAnchor, ancestors,
	realParents, isPlainChain, cardTitle, branchAnchor, dedupeFanIn, ancestorsForward,
}

// vim: set noet ts=4 sw=4:
