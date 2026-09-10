<template>
	<div>
		<aquapi-wiring></aquapi-wiring>
	</div>
</template>

<script>
import {useWiringStore} from 'store/wiring'

export default {
	name: 'Wiring',

	beforeRouteLeave(to, from, next) {
		const wiringStore = useWiringStore()
		if (!wiringStore.draftDirty) {
			next()
			return
		}
		this.$confirm(this.$t('pages.wiring.confirmLeaveUnsaved'), {
			confirmLabel: this.$t('pages.wiring.saveChanges'),
			extraAction: {
				label: this.$t('pages.wiring.discard'),
				color: 'error',
				value: 'discard',
			},
		}).then(async (result) => {
			if (result === true) {
				const saveResult = await wiringStore.saveDraft()
				if (saveResult.ok) {
					next()
				} else {
					this.$toast.error(saveResult.error || this.$t('misc.toast.saveError'))
					next(false)
				}
			} else if (result === 'discard') {
				wiringStore.discardDraft()
				next()
			} else {
				next(false)
			}
		})
	},
}
</script>
