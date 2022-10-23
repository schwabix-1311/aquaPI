/* This is the reactive Vue app to render interior of / <div id="vm">  AKA /home
 *
 * We do not use a build step!
 * Page is composed in Flask/Jinja, reactivity and backend synchronization are handled by Vue.
 *
 * Vue components matching the bus nodes are in v-comps.js.
 */


// the equivalent to an 'app' of a full Vue, this enables Vue inside <div id='vm'>
const vm = new Vue({
    el: '#vm',
    delimiters: ['[[', ']]'],

    // Could use a v-for loop with <component :is="comp_name" ...></component>, but
    // would need to have the type name, for now this created in Jinja template
    // template: `<div class="uk-child-width-1-2@s uk-grid-small" uk-grid>
    //              <div v-for="id in ['wasser', 'beleuchtung']">
    //                <component :is="BusNode" id=[[id]] ref=[[id]]></component><br/>
    //              </div>
    //              <bus-node id='wasser' ref='wasser'></bus-node><br/>
    //              <bus-node id='temperatur' ref='temperatur'></bus-node><br/>
    //            </div>
    //            `,
    template: '#vueHome',

    methods: {
        // https://stackoverflow.com/questions/61535713/accessing-vue-component-from-outside
        async updateNode(id) {
            if (id in this.$refs) {
                const newNode = await getNode(id)
                console.debug(`updateNode(${id}): ` + newNode['data'])
                this.$refs[id].node = newNode
            }
            else {
                console.warn(`updateNode(${id}): no $ref found - missing the ref spec?`)
            }
        }
    }
})


async function getNode(id) {
  const response = await fetch('/api/node/' + id)
  return await response.json()
}


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
