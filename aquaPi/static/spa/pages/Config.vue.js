const Config = {
	template: `
		<v-card elevation="0" tile>
			<aquapi-page-heading 
				:heading="$t('pages.config.heading')" 
				icon="mdi-cog-outline"
			></aquapi-page-heading>
			
		    <v-card-text>
				<v-row justify="start">
					<v-col :cols="12">
						<v-alert
							dismissible
							border="left"
							elevation="3"
							type="info"
							YYtext
							:icon="'mdi-alert'"
							YYcolor="'orange'"
						>
							<div class="font-weight-bold">Große Baustelle!</div>
							<div>
								Will be a page to show and modify <strong>structure of nodes + drivers</strong>.<br>
								Some of it should be protected by authentication.
							</div>
						</v-alert>     
					</v-col>
				</v-row>	
				
				<v-sheet 
				    v-for="node in nodes"
				    :key="node.id"
				    outlined
				    class="my-1"
				>
<!--					{{ node }}		-->
					<div class="d-flex flex-row flex-nowrap justify-space-between">
						<div class="font-weight-medium">
							<h3>
								{{ node.name }} 
								<span class="font-weight-light">
									[{{node.id}}]
									{{ node.identifier }}
									| {{ node.type }}
									| {{ node.role }}
									| data: {{ node.data}} {{ node.unit}} {{ node.data_range }}
								</span>
							</h3>
	
							<template v-if="node.inputs">
								<v-sheet outlined class="ba-1 ml-7">
									<h5>INPUTS:</h5>
<!--									{{ node.inputs }}-->
									<ul>
										<li v-for="item in node.inputs.sender">
											<h3>
												{{ nodeItem(item).name }} 
												<span class="font-weight-light">
													[{{ nodeItem(item).id }}]
													{{ nodeItem(item).identifier }}
													| {{ nodeItem(item).type }}
													| {{ nodeItem(item).role }}
													| data: {{ nodeItem(item).data}} {{ nodeItem(item).unit}} {{ nodeItem(item).data_range }}
												</span>
											</h3>
<!--											{{ $store.getters['dashboard/node'](item) }}								-->
										</li>
									</ul>
								</v-sheet>
							</template>
						</div>
					</div>
                </v-sheet>
				
			</v-card-text>
				        
		</v-card>
    `,

	computed: {
		nodes() {
			return this.$store.getters['dashboard/nodes']
		},
		nodeItem() {
			return nodeId => {
				return this.$store.getters['dashboard/node'](nodeId)
			}
		},
		fullName(){
			return nodeId => {
				return this.$store.getters['dashboard/node'](nodeId)
			}
		}
	}
};

export { Config };