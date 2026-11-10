// Liveness rule for the SSE connection (App.vue.js).
// Pure - unit-tested in tests/js/sseWatchdog.test.js, no Vue/store.
//
// The server sends a 'ping' event after 20 s without node changes, so a
// healthy connection never stays silent much longer than that. A client
// that suspended (laptop lid, hibernate) can resume with an EventSource
// that still reports OPEN although its TCP connection died - neither
// readyState, onerror nor visibilitychange reliably reveal that (the tab
// may have stayed visible across the suspend). Only the missing pings do.

export const SERVER_PING_MS = 20_000

// three missed pings, plus slack for the server's 1 s send delay
export const STALE_AFTER_MS = 3 * SERVER_PING_MS + 5_000

// how often App.vue.js checks
export const CHECK_EVERY_MS = 10_000

export function sseIsStale(now, lastActivity) {
	return now - lastActivity > STALE_AFTER_MS
}

// vim: set noet ts=4 sw=4:
