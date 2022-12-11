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
                    const response = await fetch('/api/nodes/' + id)
                    const node = await response.json()
                    this.setNode(id, node)
                }
            }
        },
    },
};

const Dashboard = {
    delimiters: ['[[', ']]'],
    props: ['all_tiles'],
    data: function() {
        return {
            tiles: this.all_tiles,
            apiEndpoint: '/api/config/dashboard'
        };
    },
    // Preload all nodes, not required, but looks nicer
    created: async function () {
        for (t of this.all_tiles) {
          await this.$root.updateNode(t.id, true)
        }
    },
    methods: {
        persistConfig: async function() {
            const vm = this;
            const response = await fetch(this.apiEndpoint, {
                method: 'post',
                mode: 'same-origin',
                cache: 'no-cache',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                redirect: 'follow',
                body: JSON.stringify(vm.tiles)
            });

            const body = await response.json();
            if (response.status == 200) {
                UIkit.modal(vm.$refs.modal).hide();
                UIkit.notification({message: `<span uk-icon=\'icon: check\'></span> ${body.resultMsg}`, status: 'success'});
            } else {
                UIkit.modal(vm.$refs.modal).hide();
                UIkit.notification({message: `<span uk-icon=\'icon: warning\'></span> ${body.resultMsg}`, status: 'danger'});
            }
        },
        fetchConfig: async function() {
            const response = await fetch(this.apiEndpoint, {
                method: 'get',
                mode: 'same-origin',
                cache: 'no-cache',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                },
                redirect: 'follow'
            });
            const body = await response.json();
            if (response.status == 200) {
                UIkit.notification({message: `<span uk-icon=\'icon: info\'></span> Test: fetched dashboard configuration`, status: 'primary'});
            }
            // console.log('response body:', body);
        }
    },
    template: `
        <div class="uk-child-width-1-2@s uk-grid-small" uk-grid="masonry: true">
            <div v-for="t in tiles" :hidden="(!t.vis)" >
                <component :is="t.comp" :id="t.id" ></component>
            </div>
            <div id="modal-config" uk-modal ref="modal">
                <div class="uk-modal-dialog uk-modal-body">
                    <form id="frm_dashboard_config" name="frm_dashboard_config" action="/" method="post" @submit.prevent="persistConfig" class="uk-form-horizontal">
                        <div class="uk-modal-header">
                            <h2 class="uk-modal-title">Dashboard Konfiguration</h2>
                        </div>
                        <div class="uk-modal-body">
                            <p>Which tiles should be shown?</p>
                            <div v-for="t in tiles">
                                <label>
                                    <input :key="t.comp+'.'+t.id" type="checkbox" :id="t.comp+'.'+t.id" v-model="t.vis" :name="t.comp+'.'+t.id" class="uk-checkbox uk-margin-small-right">
                                    [[ t.name ]]
                                </label>
                            </div>
                        </div>
                        <div class="uk-modal-footer uk-text-right">
                            <button type="button" class="uk-button uk-button-secondary" @click="fetchConfig">TEST GET</button>
                            <button type="submit" class="uk-button uk-button-default">Übernehmen</button>
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
