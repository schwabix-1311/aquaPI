// One place for the fetch boilerplate every store action repeated by
// hand: the same-origin/no-cache options, the X-Requested-With / Accept
// (and, when there's a body, Content-Type) headers, JSON encoding of the
// body, tolerant JSON decoding of the response, and the
// "(data.error) || 'HTTP <status>'" error string.
//
// Returns a plain result object, never throws:
//   {ok: true,  status, data}          - 2xx (data is null for 204)
//   {ok: false, status, data, error}   - non-2xx (error is a message)
//   {ok: false, status: 0, data: null, error} - network/other failure
//
// `body` is optional: omit it for GET/DELETE, pass any JSON-serialisable
// value for POST/PUT. Pass `{form: true}` as `opts` to send `body` as
// application/x-www-form-urlencoded instead - the auth store's routes
// (/login, /reset-password, ...) are plain Flask-Login form posts, not
// the JSON /api/* surface, and expect their body that way; `data` still
// comes back parsed from whatever JSON the route replies with.

export async function apiRequest(method, url, body, opts = {}) {
	const headers = {
		'X-Requested-With': 'XMLHttpRequest',
		'Accept': 'application/json',
	}
	const reqOpts = {
		method,
		mode: 'same-origin',
		cache: 'no-cache',
		headers,
	}
	if (body !== undefined) {
		if (opts.form) {
			headers['Content-Type'] = 'application/x-www-form-urlencoded'
			reqOpts.body = new URLSearchParams(body)
		} else {
			headers['Content-Type'] = 'application/json'
			reqOpts.body = JSON.stringify(body)
		}
	}

	try {
		const response = await fetch(url, reqOpts)
		// 204 (and any empty response) has no JSON body to parse
		const data = response.status === 204
			? null
			: await response.json().catch(() => null)

		if (response.ok) {
			return {ok: true, status: response.status, data}
		}
		return {
			ok: false,
			status: response.status,
			data,
			error: (data && data.error) || ('HTTP ' + response.status),
		}
	} catch (e) {
		return {ok: false, status: 0, data: null, error: e.message}
	}
}

// vim: set noet ts=4 sw=4:
