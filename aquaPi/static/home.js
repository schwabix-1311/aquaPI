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
    data () {
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
                    //TODO: error handler - might loose connection
                    const response = await fetch('/api/node/' + id)
                    const node = await response.json()
                    this.setNode(id, node)
                }
            }
        }
    }
};

const Dashboard = {
    delimiters: ['[[', ']]'],
    props: [ 'all_tiles' ],
    data: function() {
        return { tiles: this.all_tiles }
    },
    template: `
        <div class="uk-child-width-1-2@s uk-grid-small" uk-grid="masonry: true">
            <div v-for="t in tiles" :hidden="(!t.vis)" >
                <component :is="t.comp" :id="t.id" ></component>
            </div>
            <div id="modal-config" uk-modal>
    <!-- form action="/home" method="post" class="uk-form-horizontal" -->
    <!-- fieldset class="uk-fieldset" -->
                <div class="uk-modal-dialog uk-modal-body">
                    <div class="uk-modal-header">
                        <button class="uk-modal-close-default" type="button" uk-close></button>
                        <h2 class="uk-modal-title">Dashboard Configuration</h2>
                    </div>
                    <div class="uk-modal-body">
                        <p>Which tiles should be shown?</p>
                        <div v-for="t in tiles">
                            <label><input class="uk-checkbox" type="checkbox" v-model="t.vis" > [[ t.name ]]</label>
                        </div>
                    </div>
                    <div class="uk-modal-footer uk-text-right">
                        <button class="uk-button uk-button-default uk-modal-close" type="submit" onClick="acceptConfig()">Accept</button>
                    </div>
                </div>
    <!-- /fieldset -->
    <!-- /form -->
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
        console.debug(`EventSource sent: ${e.data}`);
        // this is an array of node ids that were modified
        const obj = JSON.parse(e.data);
        for (const i in obj) {
            id = obj[i]
            vm.updateNode(id)
        }
    }
}
