import {AQUAPI_EVENTS, EventBus} from './EventBus.js'

const AquapiToast = {
	name: 'AquapiToast',
	template: `
		<v-snackbar
			v-model="visible"
			:color="current ? current.color : 'success'"
			:timeout="current ? current.timeout : 4000"
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
		}
	},

	methods: {
		onRequest(payload) {
			this.queue.push(payload)
			if (!this.visible) this.showNext()
		},
		showNext() {
			if (!this.queue.length) {
				this.current = null
				this.visible = false
				return
			}
			this.current = this.queue.shift()
			this.visible = true
		},
		dismiss() {
			this.visible = false
		},
		onModelValueChange(value) {
			// fires both on manual dismiss and on the snackbar's own timeout
			if (!value) this.showNext()
		},
	},

	created() {
		EventBus.$on(AQUAPI_EVENTS.TOAST_REQUESTED, this.onRequest)
	},
	unmounted() {
		EventBus.$off(AQUAPI_EVENTS.TOAST_REQUESTED, this.onRequest)
	},
}

export {AquapiToast}

// vim: set noet ts=4 sw=4:
