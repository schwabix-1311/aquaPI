// Pure chain-layout algorithm for the /wiring canvas: given the node
// list, return a Map<id, {pos_x, pos_y}>. No Vue, no store - so it runs
// under node:test (see tests/js/wiringLayout.test.js).
//
// One row per chain (or standalone node); within a chain, column = depth
// from its root so pipeline stages line up vertically, and a node's
// first (real, non-History/Alert) listener continues its own row while
// every further listener fans out to a new row beneath - keeps sibling
// branches from overlapping in the same row.

import {NODE_BOX_WIDTH, NODE_BOX_HEIGHT} from './constants.js'
import {isRoot, isHistOrAlert, descendants, flattenEntries} from '../settings/chains.js'

const LAYOUT_COL_GAP = 70
const LAYOUT_ROW_GAP = 50

// entries: descendants()'s [{node, children}] tree at this depth;
// returns the next free row after placing this whole subtree
function assignRows(entries, depth, startRow, positions, placed, usedCells) {
	let row = startRow
	entries.forEach(entry => {
		const nodeRow = row
		row = entry.children.length
			? assignRows(entry.children, depth + 1, row, positions, placed, usedCells)
			: row + 1
		positions.set(entry.node.id, {row: nodeRow, col: depth})
		placed.add(entry.node.id)
		usedCells.add(nodeRow + ':' + depth)
	})
	return row
}

export function computeLayout(nodes) {
	const byId = {}
	nodes.forEach(n => { byId[n.id] = n })

	const positions = new Map()
	const placed = new Set()
	const usedCells = new Set()   // 'row:col' - collision guard, since
	                               // History/Alert placement below can
	                               // reuse an already-claimed row
	let nextRow = 0

	// bumps row down (same col) until free, so two nodes can never land
	// on the exact same cell; returns the row actually used
	const place = (nodeId, row, col) => {
		while (usedCells.has(row + ':' + col)) row++
		usedCells.add(row + ':' + col)
		positions.set(nodeId, {row, col})
		placed.add(nodeId)
		return row
	}

	// like place(), but bumps the COLUMN instead on a collision - for
	// History/Alert sinks, which have no listeners of their own, so
	// nudging one a slot further right is harmless. Bumping their ROW
	// instead (like place()) is a real bug: a column can be legitimately
	// reused by many unrelated chains at different rows (e.g. each happens
	// to be exactly deep enough to reach that same column), so
	// row-bumping can march a sink down through many rows that have
	// nothing to do with its own source before finding a gap - dragging
	// it far away even when fed by a node in row 0.
	const placeSink = (nodeId, row, col) => {
		while (usedCells.has(row + ':' + col)) col++
		usedCells.add(row + ':' + col)
		positions.set(nodeId, {row, col})
		placed.add(nodeId)
	}

	// Pass 1: real chain roots (empty/wildcard receives) - column = depth
	// from root. History/Alert nodes are NOT included here even though
	// isRoot() treats them as roots too (that's grouping semantics for
	// /settings, where they always get their own card) - spatially
	// they're sinks, not chain starts, handled in Pass 2 below once every
	// real node has its final position.
	// Longest chains first (by total descendant count): placing a tall
	// chain into whatever's already a dense block of short ones (rather
	// than the reverse) tends to force it further right/down than it
	// needs, fragmenting the layout more than starting with the tall ones
	// and filling shorter ones in around them. Sort key is the FLATTENED
	// descendant count - tree.length itself is only the number of direct
	// children (descendants() returns a nested {node, children} tree, not
	// a flat list), which underweights deep-but-narrow chains and left
	// equal-direct-children roots ordered by array insertion order
	// instead of actual chain size.
	const roots = nodes.filter(n => isRoot(n) && !isHistOrAlert(n))
		.map(root => ({root, tree: descendants(root, byId)}))
		.sort((a, b) => flattenEntries(b.tree).length - flattenEntries(a.tree).length)
	roots.forEach(({root, tree}) => {
		if (placed.has(root.id)) return
		place(root.id, nextRow, 0)
		const endRow = tree.length
			? assignRows(tree, 1, nextRow, positions, placed, usedCells)
			: nextRow + 1
		nextRow = Math.max(endRow, nextRow + 1)
	})

	// Pass 2: History/Alert sinks. Every real node is positioned by now,
	// so each one just drops in relative to its own (fully resolved)
	// sources - no need to track "is this one ready yet" during Pass 1,
	// and it naturally handles a sink fed by several different chains
	// too, since all of them are already placed.
	// row = the MEDIAN row among its sources, so it lands near where most
	// of them are instead of chasing whichever single source happens to
	// sit lowest. Math.max() here used to mean one short, late-placed
	// source (e.g. a leaf root chain with no descendants, sorted to the
	// very end above) could drag a sink far down even though its other
	// sources sit much higher - the sink inherited the worst case
	// instead of the typical one.
	// col = one past their rightmost column, instead of column 0 -
	// pinning it to column 0 like a real root previously sent its
	// incoming connection's target-side trunk stub
	// (targetTrunkX = pos_x - CONNECTION_STUB) to a negative x, off the
	// left edge of the canvas and invisible. Falls back to its own fresh
	// row/col 0 if nothing resolves (e.g. only `'*'`, a missing id, or no
	// receives at all).
	nodes.filter(isHistOrAlert).forEach(node => {
		const sourcePositions = (node.receives || [])
			.map(id => positions.get(id))
			.filter(Boolean)
		if (sourcePositions.length) {
			const rows = sourcePositions.map(p => p.row).sort((a, b) => a - b)
			const mid = Math.floor(rows.length / 2)
			const row = rows.length % 2
				? rows[mid]
				: Math.round((rows[mid - 1] + rows[mid]) / 2)
			const col = Math.max(...sourcePositions.map(p => p.col)) + 1
			placeSink(node.id, row, col)
		} else {
			placeSink(node.id, nextRow, 0)
			nextRow++
		}
	})

	// orphaned edge case (e.g. a receives-cycle with no root) - still give
	// any leftover node its own row rather than skipping it
	nodes.forEach(node => {
		if (placed.has(node.id)) return
		nextRow = place(node.id, nextRow, 0) + 1
	})

	const layout = new Map()
	positions.forEach((pos, nodeId) => {
		// nodes with more than one incoming connection get nudged down by
		// half their own box height - their several diagonals converge
		// from different rows, so centering on any one of those rows sends
		// at least one wire straight through the box above/below;
		// splitting the difference keeps them all visually distinct. Half
		// the box's OWN height (not half a full row) keeps this
		// unconditionally safe: even a same-column neighbor in the very
		// next row still keeps LAYOUT_ROW_GAP/2 of clearance instead of
		// overlapping it, so there's no need to check whether that cell
		// happens to be occupied first.
		const receivesCount = (byId[nodeId]?.receives || []).length
		const rowOffsetPx = receivesCount > 1 ? NODE_BOX_HEIGHT / 2 : 0
		layout.set(nodeId, {
			pos_x: pos.col * (NODE_BOX_WIDTH + LAYOUT_COL_GAP),
			pos_y: pos.row * (NODE_BOX_HEIGHT + LAYOUT_ROW_GAP) + rowOffsetPx,
		})
	})
	return layout
}

// vim: set noet ts=4 sw=4:
