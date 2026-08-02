import '../components/config/index.js'

const Config = {
	template: `
		<div>
			<aquapi-config></aquapi-config>
		</div>
	`,

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
};

export { Config };

// vim: set noet ts=4 sw=4:
