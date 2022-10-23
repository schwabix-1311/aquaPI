/* This is a collection of Vue components that match the bus nodes
 *
 * We do not use a build step!
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

