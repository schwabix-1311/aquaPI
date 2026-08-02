<template>
	<div>
		<aquapi-config></aquapi-config>
	</div>
</template>

<script>
export default {
	name: 'Config',

	beforeRouteLeave(to, from, next) {
		if (!this.$store.getters['config/draftDirty']) {
			next()
			return
		}
		this.$confirm(this.$t('pages.config.confirmLeaveUnsaved')).then(ok => {
			if (ok) {
				this.$store.dispatch('config/discardDraft')
				next()
			} else {
				next(false)
			}
		})
	},
}
</script>
