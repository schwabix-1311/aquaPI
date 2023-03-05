import './AquapiNavDrawer.vue.js'

const AquapiPageHeading = {
	template: `
		<v-toolbar flat color="transparent">
			<v-toolbar-title tag="h1" class="text-h5 d-flex align-center">
				<v-icon 
					v-if="icon" 
					color="blue-grey" 
					:class="($vuetify.theme.dark ? 'text--darken-2' : 'text--lighten-4')"
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
					color="primary"
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
Vue.component('AquapiPageHeading', AquapiPageHeading)


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
            Einfach nur 'ne Dummy-Komponente für Testzwecke
          </v-card-text>
        </v-card>
      </v-hover>
	`
}
Vue.component('AquapiDummy', AquapiDummy)

export {AquapiPageHeading, AquapiDummy}