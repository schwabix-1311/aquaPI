'use strict'

// Thin wrapper around vue3-sfc-loader's loadModule(), so callers can just
// do `() => loadSfc('/static/spa/pages/About.vue')` as an async component
// factory. Compiles .vue files entirely client-side; the Flask backend
// keeps serving them unchanged as plain static assets.

// Bump this whenever the loader/compiler version or caching semantics
// change, to invalidate previously cached compiled modules.
const CACHE_VERSION = 'v1'

// Note: vue3-sfc-loader parses plain `.js` dependencies with Babel's
// non-module ("script") sourceType, so a `.js` file using `import`/`export`
// (like this one) can't be `import`ed directly from inside a loaded SFC's
// `<script>` block. Instead, `loadSfc` itself is exposed through
// `moduleCache` (the same mechanism used for `vue` below), so SFCs that
// need to lazy-load a sub-component can do `import {loadSfc} from 'sfc/loadSfc'`.
const options = {
	moduleCache: {
		vue: Vue,
		'sfc/loadSfc': {loadSfc},
	},

	async getFile(url) {
		const res = await fetch(url)
		if (!res.ok) {
			throw new Error(url + ' ' + res.statusText)
		}
		return await res.text()
	},

	addStyle(textContent) {
		const style = document.createElement('style')
		style.textContent = textContent
		document.head.appendChild(style)
	},

	// vue3-sfc-loader's actual cache hook: `compiledCache.get/set(key, value)`,
	// where `value` is already a JSON string and `key` is loader-computed
	// (content hash), so we only need to add our own storage prefix.
	compiledCache: {
		get(key) {
			return window.localStorage.getItem('aquapi.sfc.' + CACHE_VERSION + '.' + key) || undefined
		},
		set(key, value) {
			window.localStorage.setItem('aquapi.sfc.' + CACHE_VERSION + '.' + key, value)
		},
	},
}

function loadSfc(path) {
	return window['vue3-sfc-loader'].loadModule(path, options)
}

export {loadSfc}

// vim: set noet ts=4 sw=4:
