// Which source -> target wirings the editor allows. One predicate,
// replacing the old SOURCEABLE_ROLES role whitelist plus the three
// separate, unfiltered "list every other node" pickers
// (WiringNodeDialog, NodeReceivesEditor, and the drag-connect check).
//
// Rules, keyed on data type - NOT on a hand-maintained role list, so a
// new CTRL/AUX/OUT node variant is wireable automatically:
//  - the target must accept `receives` at all (schema.receives != 'none')
//    and not be an Alert (its `receives` is derived from conditions,
//    edited through PUT /api/nodes/<id>/conditions).
//  - the source must produce usable data: not a History (posts a
//    constant keep-alive, not a real value) and not STRING-typed
//    (Alert, TextInput) - every consumer either compares the value
//    numerically or stores it in a numeric column, and none handles a
//    string. Mirrored server-side in db.source_data_range_ok().
//
// `data_range` is on every persisted node dict; for a not-yet-saved
// draft node it isn't, so fall back to the type's schema data_range.

function rangeOf(node, nodeTypes) {
	return node.data_range
		|| (nodeTypes && nodeTypes[node.type] && nodeTypes[node.type].data_range)
		|| null
}

export function targetAcceptsReceives(target, nodeTypes) {
	const schema = nodeTypes && nodeTypes[target.type]
	return !!schema && schema.receives !== 'none' && target.role !== 'ALERTS'
}

export function isUsableSource(source, nodeTypes) {
	if (!source || source.role === 'HISTORY') {
		return false
	}
	return rangeOf(source, nodeTypes) !== 'STRING'
}

// stricter: the source must produce a plain number (AlertCond does a
// float comparison; History stores into a numeric column)
export function isNumericSource(source, nodeTypes) {
	return !!source && ['ANALOG', 'PERCENT', 'BINARY'].includes(rangeOf(source, nodeTypes))
}

export function canConnect(source, target, nodeTypes) {
	return !!source && !!target && source.id !== target.id
		&& isUsableSource(source, nodeTypes)
		&& targetAcceptsReceives(target, nodeTypes)
}

// {id: node} map (or array) -> the nodes that may feed `target`
export function connectableSources(target, allNodes, nodeTypes) {
	const list = Array.isArray(allNodes) ? allNodes : Object.values(allNodes || {})
	return list.filter(n => canConnect(n, target, nodeTypes))
}

// vim: set noet ts=4 sw=4:
