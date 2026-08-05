<template>
	<div>
		<aquapi-config></aquapi-config>
	</div>
</template>

<script>
import {useConfigStore} from 'store/config'

export default {
	name: 'Config',

	beforeRouteLeave(to, from, next) {
		const configStore = useConfigStore()
		if (!configStore.draftDirty) {
			next()
			return
		}
		this.$confirm(this.$t('pages.config.confirmLeaveUnsaved')).then(ok => {
			if (ok) {
				configStore.discardDraft()
				next()
			} else {
				next(false)
			}
		})
	},
}
</script>
