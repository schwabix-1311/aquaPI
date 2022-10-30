/* This is the reactive Vue app to render interior 
 * of / <div id="vm"> AKA /home
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
            nodes: {}
        }
    },
    template: '#vueHome',
    methods: {
        setNode(id, node) {
            Vue.set(this.nodes, id, node)
        },
        async updateNode(id, addNew=false) {
            if ((id in this.nodes) | addNew) {
                //TODO: error handler - might loose connection
                const response = await fetch('/api/node/' + id)
                const node = await response.json()
                this.setNode(id, node)
            }
        }
    }
};

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
