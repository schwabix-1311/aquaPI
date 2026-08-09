const AppFooComp = {
	name: 'AppFooComp',
	template: `<div class="text-caption">
		<template v-for="(part, idx) in parts" :key="idx">
			<span v-if="idx > 0"> | </span>
			<span :style="part.color ? {color: part.color} : null">{{ part.text }}</span>
		</template>
	</div>`,
	data: () => ({stats: null}),
	computed: {
		parts() {
			if (!this.stats) return []
			// load1/mem_used_pct/disk_used_pct come back null on platforms
			// lacking that stat (e.g. a Windows dev box) - just omit the
			// segment rather than showing a broken/empty value
			const parts = []
			parts.push({text: this.$t('misc.footer.servedBy', {os: this.stats.os})})
			if (this.stats.hw_model) {
				parts.push({text: this.$t('misc.footer.platform', {model: this.stats.hw_model})})
			}
			if (this.stats.load1 !== null && this.stats.cpu_count) {
				const pct = this.stats.load1 / this.stats.cpu_count * 100
				parts.push({
					text: this.$t('misc.footer.load', {load: this.stats.load1, cores: this.stats.cpu_count}),
					color: this.severityColor(pct),
				})
			}
			if (this.stats.mem_used_pct !== null) {
				parts.push({
					text: this.$t('misc.footer.ram', {pct: this.stats.mem_used_pct}),
					color: this.severityColor(this.stats.mem_used_pct),
				})
			}
			if (this.stats.disk_used_pct !== null) {
				parts.push({
					text: this.$t('misc.footer.disk', {pct: this.stats.disk_used_pct}),
					color: this.severityColor(this.stats.disk_used_pct),
				})
			}
			return parts
		},
	},
	methods: {
		severityColor(pct) {
			const colors = this.$vuetify.theme.global.current.colors
			if (pct > 90) return colors.error
			if (pct > 80) return colors.warning
			return null
		},
		async refresh() {
			const res = await fetch('/api/system-info')
			if (res.ok) this.stats = await res.json()
		},
	},
	mounted() {
		this.refresh()
		this._interval = window.setInterval(this.refresh, 10000)
	},
	unmounted() {
		window.clearInterval(this._interval)
	},
};

export {AppFooComp};

// vim: set noet ts=4 sw=4:
