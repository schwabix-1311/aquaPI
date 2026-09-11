// Unit tests for apiRequest.js - the shared fetch wrapper every Pinia
// store action uses instead of hand-rolling the same boilerplate.
// Run: node --test "tests/js/**/*.test.js"

import test from 'node:test'
import assert from 'node:assert/strict'

import {apiRequest} from '../../aquaPi/static/spa/store/apiRequest.js'

function fakeResponse({status = 200, json = null, jsonThrows = false} = {}) {
	return {
		status,
		ok: status >= 200 && status < 300,
		json: async () => {
			if (jsonThrows) {
				throw new SyntaxError('Unexpected end of JSON input')
			}
			return json
		},
	}
}

function withFetch(impl, run) {
	const orig = globalThis.fetch
	globalThis.fetch = impl
	return run().finally(() => { globalThis.fetch = orig })
}

test('2xx -> {ok:true, status, data}', async () => {
	await withFetch(
		async () => fakeResponse({status: 200, json: {a: 1}}),
		async () => {
			const res = await apiRequest('get', '/api/x')
			assert.deepEqual(res, {ok: true, status: 200, data: {a: 1}})
		})
})

test('204 -> data is null without calling .json()', async () => {
	await withFetch(
		async () => fakeResponse({status: 204, jsonThrows: true}),
		async () => {
			const res = await apiRequest('delete', '/api/x/1')
			assert.deepEqual(res, {ok: true, status: 204, data: null})
		})
})

test('non-2xx with a JSON {error} body uses that message', async () => {
	await withFetch(
		async () => fakeResponse({status: 400, json: {error: 'bad value'}}),
		async () => {
			const res = await apiRequest('post', '/api/x', {v: 1})
			assert.equal(res.ok, false)
			assert.equal(res.status, 400)
			assert.equal(res.error, 'bad value')
			assert.deepEqual(res.data, {error: 'bad value'})
		})
})

test('non-2xx with an unparseable/empty body falls back to "HTTP <status>"', async () => {
	await withFetch(
		async () => fakeResponse({status: 404, jsonThrows: true}),
		async () => {
			const res = await apiRequest('get', '/api/x/gone')
			assert.equal(res.ok, false)
			assert.equal(res.status, 404)
			assert.equal(res.data, null)
			assert.equal(res.error, 'HTTP 404')
		})
})

test('a network failure (fetch rejects) -> status 0, never throws', async () => {
	await withFetch(
		async () => { throw new TypeError('Failed to fetch') },
		async () => {
			const res = await apiRequest('get', '/api/x')
			assert.deepEqual(res, {ok: false, status: 0, data: null, error: 'Failed to fetch'})
		})
})

test('a JSON body is sent as application/json by default', async () => {
	let seen
	await withFetch(
		async (url, opts) => { seen = {url, opts}; return fakeResponse({status: 200, json: null}) },
		async () => { await apiRequest('post', '/api/x', {a: 1}) })
	assert.equal(seen.opts.headers['Content-Type'], 'application/json')
	assert.equal(seen.opts.body, JSON.stringify({a: 1}))
})

test('{form: true} sends the body as application/x-www-form-urlencoded', async () => {
	let seen
	await withFetch(
		async (url, opts) => { seen = {url, opts}; return fakeResponse({status: 200, json: {result: 'SUCCESS'}}) },
		async () => { await apiRequest('post', '/login', {username: 'a', password: 'b'}, {form: true}) })
	assert.equal(seen.opts.headers['Content-Type'], 'application/x-www-form-urlencoded')
	assert.ok(seen.opts.body instanceof URLSearchParams)
	assert.equal(seen.opts.body.toString(), 'username=a&password=b')
})

test('no body (GET/DELETE) sends no Content-Type header and no body', async () => {
	let seen
	await withFetch(
		async (url, opts) => { seen = {url, opts}; return fakeResponse({status: 200, json: []}) },
		async () => { await apiRequest('get', '/api/x') })
	assert.equal(seen.opts.headers['Content-Type'], undefined)
	assert.equal(seen.opts.body, undefined)
})

// vim: set noet ts=4 sw=4:
