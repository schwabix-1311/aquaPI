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
			// the theme's error/warning swatches are tuned to pop as fills
			// against a dark surface (or pair with on-error/on-warning text);
			// used as plain text on the light theme's white background they
			// fail contrast (warning #FFC107 is ~1.6:1 - near invisible), so
			// light mode gets darker, WCAG-AA-legible stand-ins here instead
			const dark = this.$vuetify.theme.global.current.dark
			if (pct > 90) return dark ? '#FF5252' : '#C62828'
			if (pct > 80) return dark ? '#FFC107' : '#E65100'
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
