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
		this.$confirm(this.$t('pages.config.confirmLeaveUnsaved'), {
			confirmLabel: this.$t('pages.config.saveChanges'),
			extraAction: {
				label: this.$t('pages.config.discard'),
				color: 'error',
				value: 'discard',
			},
		}).then(async (result) => {
			if (result === true) {
				const saveResult = await configStore.saveDraft()
				if (saveResult.ok) {
					next()
				} else {
					this.$toast.error(saveResult.error || this.$t('misc.toast.saveError'))
					next(false)
				}
			} else if (result === 'discard') {
				configStore.discardDraft()
				next()
			} else {
				next(false)
			}
		})
	},
}
</script>
