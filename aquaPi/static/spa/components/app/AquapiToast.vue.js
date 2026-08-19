import {AQUAPI_EVENTS, EventBus} from './EventBus.js'

const AquapiToast = {
	name: 'AquapiToast',
	template: `
		<v-snackbar
			v-model="visible"
			:color="current ? current.color : 'success'"
			:timeout="-1"
			location="bottom"
			@update:model-value="onModelValueChange"
		>
			{{ current ? current.message : '' }}
			<template #actions>
				<v-btn variant="text" @click="dismiss">{{ $t('misc.dialog.ok') }}</v-btn>
			</template>
		</v-snackbar>
	`,

	data() {
		return {
			queue: [],
			current: null,
			visible: false,
			dismissTimer: null,
		}
	},

	methods: {
		onRequest(payload) {
			this.queue.push(payload)
			if (!this.visible) this.showNext()
		},
		showNext() {
			clearTimeout(this.dismissTimer)
			if (!this.queue.length) {
				this.current = null
				this.visible = false
				return
			}
			this.current = this.queue.shift()
			this.visible = true
			// v-snackbar's own :timeout is disabled (-1) - its internal
			// auto-dismiss watcher wasn't reliably re-arming itself on
			// every subsequent toast in this app (confirmed live: no
			// window.setTimeout call for it at all past the first one),
			// so this component owns the dismiss timer outright instead.
			this.dismissTimer = setTimeout(() => this.dismiss(), this.current.timeout || 4000)
		},
		dismiss() {
			clearTimeout(this.dismissTimer)
			this.visible = false
		},
		onModelValueChange(value) {
			// fires on manual dismiss (the OK button); the auto-dismiss
			// path now goes through dismiss() -> this same setter, not
			// through v-snackbar's own timeout (disabled above)
			if (!value) this.showNext()
		},
	},

	created() {
		EventBus.$on(AQUAPI_EVENTS.TOAST_REQUESTED, this.onRequest)
	},
	unmounted() {
		EventBus.$off(AQUAPI_EVENTS.TOAST_REQUESTED, this.onRequest)
		clearTimeout(this.dismissTimer)
	},
}

export {AquapiToast}

// vim: set noet ts=4 sw=4:
