// Unit tests for sseWatchdog.sseIsStale - when App.vue.js replaces its
// EventSource.
// Run: node --test "tests/js/**/*.test.js"

import test from 'node:test'
import assert from 'node:assert/strict'

import {sseIsStale, SERVER_PING_MS, STALE_AFTER_MS, CHECK_EVERY_MS}
	from '../../aquaPi/static/spa/components/app/sseWatchdog.js'

test('a quiet connection that still gets pings is not stale', () => {
	assert.equal(sseIsStale(1_000_000 + SERVER_PING_MS + 1_000, 1_000_000), false)
	assert.equal(sseIsStale(1_000_000 + 2 * SERVER_PING_MS + 2_000, 1_000_000), false)
})

test('three missed pings make it stale', () => {
	assert.equal(sseIsStale(1_000_000 + STALE_AFTER_MS + 1, 1_000_000), true)
})

test('hours of suspend are caught by the first check after resume', () => {
	const fourHours = 4 * 3600 * 1000
	assert.equal(sseIsStale(1_000_000 + fourHours, 1_000_000), true)
	assert.ok(CHECK_EVERY_MS < STALE_AFTER_MS)
})

// vim: set noet ts=4 sw=4:
