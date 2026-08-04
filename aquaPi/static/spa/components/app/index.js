import './AquapiNavDrawer.vue.js'
import {registerGlobalComponent} from './registry.js'

const AquapiPageHeading = {
	template: `
		<v-toolbar flat color="transparent">
			<v-toolbar-title tag="h1" class="text-h5 d-flex align-center">
				<v-icon 
					v-if="icon" 
					color="blue-grey" 
					:class="($vuetify.theme.global.current.dark ? 'text--darken-2' : 'text--lighten-4')"
					left
				>
					{{ icon }}
				</v-icon>
				{{ heading }}
			</v-toolbar-title>
			<template v-if="buttons">
				<v-spacer></v-spacer>
				<v-btn v-for="item, idx in buttons" :key="idx"
					icon
					variant="text"
					color="grey-darken-1"
					@click="item.action"
				>
					<v-icon>{{ item.icon }}</v-icon>
				</v-btn>
			</template>
		</v-toolbar>
	`,
	props: {
		heading: {
			type: String,
			required: true
		},
		icon: {
			type: String,
			required: false,
			default: null
		},
		buttons: {
			type: Array,
			required: false,
			default: () => []
		}
	}
}
registerGlobalComponent('AquapiPageHeading', AquapiPageHeading)

const AquapiLoadingIndicator = {
	template: `
		<v-progress-circular
			:size="size"
			:width="width"
			indeterminate
			:color="color"
		></v-progress-circular>
	`,
	props: {
		size: {
			type: Number,
			default: 50,
			required: false
		},
		width: {
			type: Number,
			default: 6,
			required: false
		},
		color: {
			type: String,
			default: 'primary',
			required: false
		}
	}
}
registerGlobalComponent('AquapiLoadingIndicator', AquapiLoadingIndicator)
const AquapiDummy = {
	template: `
		<v-hover
			v-slot="{ hover }"
		>
			<v-card
				:elevation="hover ? 8 : 2"
				:color="hover ? 'yellow' : 'orange lighten-3'"
				class="mx-auto text--black"
				max-width="350"
			>
				<v-card-text class="my-4 text-center text-h6">
					{{ $t('misc.dummyComponentText') }}
				</v-card-text>
			</v-card>
		</v-hover>
	`
}
registerGlobalComponent('AquapiDummy', AquapiDummy)

export {AquapiPageHeading, AquapiDummy}

// vim: set noet ts=4 sw=4:
