/* This is a collection of Vue components that match the bus nodes
 *
 * We do not use a build step!
 *
 * Each type of bus node should have a matching type of Vue component,
 * however there will be a mechanism to fall back on anchestors, to allow
 * quick implementation (import?) of new nodes W/O a Vue component
 */

const AnyNode = {
    delimiters: ['[[', ']]'],
    props: {
        id: String
    },
    async beforeMount () {
        this.$root.updateNode(this.id, addNew=true)
    },
    computed: {
        node() {
            if (this.id in this.$root.nodes)
                return this.$root.nodes[this.id]
            // may be undefined beforeMount
            return undefined
        },
    },
};

const DebugNode = {
    extends: AnyNode,
    template: `
          <div class="uk-card uk-card-small uk-card-default">
            <div class="uk-card-header">
              <h2 class="uk-card-title uk-margin-remove-bottom">
                [[ id ]] - raw:
              </h2>
            </div>
            <div class="uk-card-body uk-padding-remove">
              <div class="uk-grid-collapse" uk-grid>
                <div>
                  [[ $root.nodes[id] ]]
                </div>
              </div>
            </div>
          </div>
    `
};
Vue.component('DebugNode', DebugNode);

const BusNode = {
    extends: AnyNode,
    computed: {
        getLabel() {
            return this.node?.render_data['label']
        },
        getPrettyData() {
            try {
                return this.node?.render_data['pretty_data']
            }
            catch {
                return this.node?.data.toFixed(2)
            }
        },
        getAlert() {
            if ((this.node === undefined) || !('alert' in this.node.render_data))
                return ''
            return this.node.render_data['alert'][0]
        },
        getAlertClass() {
            if ((this.node === undefined) || !('alert' in this.node.render_data))
                return ''
            const severity_map = { 'act': 'uk-label-success'
                                 , 'wrn': 'uk-label-warning'
                                 , 'err': 'uk-label-danger'
                                 , 'std': 'uk-label-default'
                                 }
            let ret = "uk-card-badge uk-label "
            severity = this.node.render_data['alert'][1]
            try {
                ret += severity_map[severity]
            }
            catch {
                console.warn('Unknown alert severity: "' + severity + '" used by ' + this.id)
            }
            return ret
        }
    },
    template: `
          <div class="uk-card uk-card-small uk-card-default">
            <div class="uk-card-header">
              <h2 class="uk-card-title uk-margin-remove-bottom">
                <span v-if="node != undefined">[[ node.name ]]</span>
                <span v-else>[[ id ]] loading ...</span>
              </h2>
              <div :hidden="!getAlert">
                <div v-bind:class="getAlertClass">[[ getAlert ]]</div>
              </div
            </div>
            <div v-if="node != undefined" class="uk-card-body uk-padding-remove">
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
};
Vue.component('BusNode', BusNode);
