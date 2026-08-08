const AppFooComp = {
	name: 'AppFooComp',
	template: `<div class="text-caption">{{ text }}</div>`,
	data: () => ({stats: null}),
	computed: {
		text() {
			if (!this.stats) return ''
			// load1/mem_used_pct/disk_used_pct come back null on platforms
			// lacking that stat (e.g. a Windows dev box) - just omit the
			// segment rather than showing a broken/empty value
			const parts = []
			parts.push(this.$t('misc.footer.servedBy', {os: this.stats.os}))
			if (this.stats.hw_model) {
				parts.push(this.$t('misc.footer.platform', {model: this.stats.hw_model}))
			}
			if (this.stats.load1 !== null && this.stats.cpu_count) {
				parts.push(this.$t('misc.footer.load', {load: this.stats.load1, cores: this.stats.cpu_count}))
			}
			if (this.stats.mem_used_pct !== null) {
				parts.push(this.$t('misc.footer.ram', {pct: this.stats.mem_used_pct}))
			}
			if (this.stats.disk_used_pct !== null) {
				parts.push(this.$t('misc.footer.disk', {pct: this.stats.disk_used_pct}))
			}
			return parts.join(' | ')
		},
	},
	methods: {
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
