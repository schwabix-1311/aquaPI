/* This is the reactive Vue app to render interior of /settings  <div id="vm">
 *
 * We do not use a build step! Page is composed in Flask/Jinja, 
 * just reactivity and backend synchronization are handled by Vue.
 *
 * Each type of bus node should have a matching type of Vue component,
 * however there will be a mechanism to fall back on anchestors, to allow
 * quick implementation (import?) of new nodes W/O a Vue component
 */

Vue.component( 'BusNode', {
    delimiters: ['[[', ']]'],
    props: {
        id: String
    },
    async beforeMount () {
        this.node = await getNode(this.id)
    },
    data() {
        return { 
            node: null
        }
    },
    computed: {
        getLabel() {
            let ret = ''
            if (this.node)
                try {
                    ret = this.node.render_data['label']
                }
                catch {
                    ret = ""
                }
            return ret
        },
        getPrettyData() {
            let ret = ''
            if (this.node)
                try {
                    ret = this.node.render_data['pretty_data']
                }
                catch {
                    ret = this.node.data.toFixed(2)
                }
            return ret
        },
        getAlert() {
            try {
                ret = this.node.render_data['alert'][0]
            }
            catch {
                ret = null
            }
            return ret
        },
        getAlertClass() {
            try {
                const severity_map = { 'act': 'uk-label-success'
                                     , 'wrn': 'uk-label-warning'
                                     , 'err': 'uk-label-danger'
                                     , 'std': 'uk-label-default'
                                     }
                severity = this.node.render_data['alert'][1]
                ret = "uk-card-badge uk-label "
                try {
                    ret += severity_map[severity]
                }
                catch {
                    console.warn('Unknown alert severity: "' + severity + '" used by ' + this.node.id)
                }
            }
            catch {
                ret = null
            }
            return ret
        }
    },
    template: `
          <div class="uk-card uk-card-small uk-card-default">
            <div class="uk-card-header">
              <h2 class="uk-card-title uk-margin-remove-bottom">
                <span v-if="node">[[ node.name ]]</span>
                <span v-else>[[ id ]] loading ...</span>
              </h2>
              <div :hidden="!getAlert">
                <div v-bind:class="getAlertClass">[[ getAlert ]]</div>
              </div
            </div>
            <div v-if="node" class="uk-card-body uk-padding-remove">
              <div class="uk-grid-collapse" uk-grid>
                <div class="uk-width-2-3">
                  [[ getLabel ]]
                </div
                <div class="uk-width-expand">
                  [[ getPrettyData ]]
                </div>
              </div>
            </div>
          </div>
    `
})


// the equivalent to an 'app' of a full Vue, this will Vue effects to <div id='vm'>
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
