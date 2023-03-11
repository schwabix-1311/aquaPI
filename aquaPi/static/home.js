/* This is the reactive Vue app to render interior 
 * of / <div id="vm"> AKA /home AKA Dashboard
 *
 * We do not use a build step!
 * Page is composed in Flask/Jinja, reactivity and backend
 * synchronization are handled by Vue.
 *
 * Vue components matching the bus nodes are in v-comps.js.
 */

const App = {
	el: '#vm',
	delimiters: ['[[', ']]'],
	data: function () {
		return {
			nodes: {},
		}
	},
	template: '#vueHome',
	methods: {
		setNode(id, node) {
			Vue.set(this.nodes, id, node)
		},
		async updateNode(id, addNew=false) {
			if (id != null) {
				if ((id in this.nodes) || addNew) {
					// TODO: error handler - might loose connection
					// console.debug(`fetch ${id} ${addNew} ...`)
					const response = await fetch('/api/nodes/' + id)
					const node = await response.json()
					this.setNode(id, node.data)
					// console.debug(`... fetch ${id} ${addNew} done`)
				}
			}
		},
	},
};

const Dashboard = {
	delimiters: ['[[', ']]'],
	props: [ 'all_tiles' ],
	data: function() {
		return { tiles: this.all_tiles }
	},
	// Preload all nodes, not required, but looks nicer
	created: async function () {
		for (t of this.all_tiles) {
		  await this.$root.updateNode(t.id, true)
		}
	},
	methods: {
		acceptConfig() {
			const form = document.getElementById("home_config");
			form.submit()
			// in case of error, the POST handler redirects away
			UIkit.notification({message: 'Konfiguration gespeichert!', status: 'success'})
		},
	},
	template: `
		<div class="uk-child-width-1-2@s uk-grid-small" uk-grid="masonry: true">
			<div v-for="t in tiles" :hidden="(!t.vis)" >
				<component :is="t.comp" :id="t.id" ></component>
			</div>
			<div id="modal-config" uk-modal>
				<div class="uk-modal-dialog uk-modal-body">
					<form action="/" method="post" id="home_config" class="uk-form-horizontal">
						<div class="uk-modal-header">
							<h2 class="uk-modal-title">Dashboard Konfiguration</h2>
						</div>
						<div class="uk-modal-body">
							<p>Which tiles should be shown?</p>
							<div v-for="t in tiles">
								<label>
									<input type="checkbox" v-model="t.vis" :name="t.comp+'.'+t.id" class="uk-checkbox uk-margin-small-right">
									[[ t.name ]]
								</label>
							</div>
						</div>
						<div class="uk-modal-footer uk-text-right">
							<input type="submit" value="Übernehmen" class="uk-button uk-button-default uk-modal-close" @click="acceptConfig">
						</div>
					</form>
				</div>
			</div>
		</div>
	`
};
Vue.component('Dashboard', Dashboard);


const vm = new Vue(App);

//vm.config.errorHandler = (err) => { /*TODO*/ }


if (!!window.EventSource) {
	const source = new EventSource(document.URL);

	source.onmessage = function(e) {
		//console.debug(`EventSource sent: ${e.data}`);
		// this is an array of node ids that were modified
		const obj = JSON.parse(e.data);
		for (const i in obj) {
			vm.updateNode(obj[i])
		}
	}
}

// vim: set noet ts=4 sw=4:
