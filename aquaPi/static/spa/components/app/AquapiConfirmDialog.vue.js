import {AQUAPI_EVENTS, EventBus} from './EventBus.js'
import {useUiStore} from '../../store/modules/ui.js'

const AquapiConfirmDialog = {
	name: 'AquapiConfirmDialog',
	template: `
		<v-dialog
			v-model="visible"
			persistent
			max-width="450px"
			:overlay-opacity="uiStore.overlay.opacity"
		>
			<v-card>
				<v-card-title v-if="title">{{ title }}</v-card-title>
				<v-card-text class="pt-4" style="white-space: pre-line;">{{ message }}</v-card-text>
				<v-card-actions>
					<v-spacer></v-spacer>
					<v-btn v-if="!alertOnly" text @click="onCancel">{{ $t('misc.dialog.cancel') }}</v-btn>
					<v-btn v-if="extraAction" :color="extraAction.color || 'primary'" text @click="onExtra">{{ extraAction.label }}</v-btn>
					<v-btn :color="confirmColor" text @click="onConfirm">{{ confirmLabel || (alertOnly ? $t('misc.dialog.ok') : $t('misc.dialog.confirm')) }}</v-btn>
				</v-card-actions>
			</v-card>
		</v-dialog>
	`,

	data() {
		return {
			visible: false,
			title: '',
			message: '',
			alertOnly: false,
			confirmLabel: null,
			confirmColor: 'primary',
			extraAction: null,
			resolve: null,
		}
	},

	computed: {
		uiStore() {
			return useUiStore()
		},
	},

	methods: {
		onRequest(payload) {
			this.title = (payload.options && payload.options.title) || ''
			this.message = payload.message
			this.alertOnly = !!(payload.options && payload.options.alertOnly)
			this.confirmLabel = (payload.options && payload.options.confirmLabel) || null
			this.confirmColor = (payload.options && payload.options.confirmColor) || 'primary'
			this.extraAction = (payload.options && payload.options.extraAction) || null
			this.resolve = payload.resolve
			this.visible = true
		},
		onConfirm() {
			this.settle(true)
		},
		onCancel() {
			this.settle(false)
		},
		onExtra() {
			this.settle(this.extraAction.value)
		},
		settle(value) {
			this.visible = false
			const resolve = this.resolve
			this.resolve = null
			if (resolve) resolve(value)
		},
	},

	created() {
		EventBus.$on(AQUAPI_EVENTS.CONFIRM_REQUESTED, this.onRequest)
	},
	unmounted() {
		EventBus.$off(AQUAPI_EVENTS.CONFIRM_REQUESTED, this.onRequest)
	},
}

export {AquapiConfirmDialog}

// vim: set noet ts=4 sw=4:
