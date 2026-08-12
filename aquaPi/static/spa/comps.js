const AppFooComp = {
	name: 'AppFooComp',
	template: `<div class="text-caption" ref="footerText">
		<template v-for="(part, idx) in visibleTextParts" :key="'t'+idx">
			<span v-if="idx > 0"> | </span>
			<span>{{ part.text }}</span>
		</template>
		<span v-if="visibleTextParts.length && visibleStatParts.length"> | </span>
		<span class="text-no-wrap">
			<template v-for="(part, idx) in visibleStatParts" :key="'s'+idx">
				<span v-if="idx > 0"> | </span>
				<span :style="part.color ? {color: part.color} : null" :title="part.label">
					<v-icon v-if="part.icon" size="14">{{ part.icon }}</v-icon>
					{{ part.text }}
				</span>
			</template>
		</span>
	</div>`,
	data: () => ({stats: null, hideLevel: 0}),
	computed: {
		// two separate groups so the stat icons+values (CPU/RAM/swap/disk)
		// can be kept together as a single `text-no-wrap` unit in the
		// template - it wraps to its own line as a whole rather than
		// splitting mid-group, while the OS/platform text ahead of it
		// still wraps normally
		textParts() {
			if (!this.stats) return []
			// drop: priority order for hiding segments before the footer
			// wraps to a 3rd line (lower = dropped first, see checkOverflow())
			const parts = [{text: this.$t('misc.footer.servedBy', {os: this.stats.os}), drop: 1}]
			if (this.stats.hw_model) {
				parts.push({text: this.$t('misc.footer.platform', {model: this.stats.hw_model}), drop: 2})
			}
			return parts
		},
		statParts() {
			if (!this.stats) return []
			// load1/mem_used_pct/swap_used_pct/disk_used_pct come back null
			// on platforms lacking that stat (e.g. a Windows dev box) or,
			// for swap, when none is configured at all - just omit the
			// segment rather than showing a broken/meaningless value.
			// CPU/RAM have no `drop` tag, they're never hidden.
			const parts = []
			if (this.stats.load1 !== null && this.stats.cpu_count) {
				const pct = Math.round(this.stats.load1 / this.stats.cpu_count * 100)
				parts.push({
					icon: 'mdi-cpu-64-bit',
					label: this.$t('misc.footer.cpuLabel'),
					text: this.$t('misc.footer.pct', {pct}),
					color: this.severityColor(pct),
				})
			}
			if (this.stats.mem_used_pct !== null) {
				parts.push({
					icon: 'mdi-memory',
					label: this.$t('misc.footer.ramLabel'),
					text: this.$t('misc.footer.pct', {pct: this.stats.mem_used_pct}),
					color: this.severityColor(this.stats.mem_used_pct),
				})
			}
			if (this.stats.swap_used_pct !== null) {
				parts.push({
					icon: 'mdi-swap-horizontal',
					label: this.$t('misc.footer.swapLabel'),
					text: this.$t('misc.footer.pct', {pct: this.stats.swap_used_pct}),
					// swap pressure matters much sooner than RAM/disk pressure
					color: this.severityColor(this.stats.swap_used_pct, 25, 50),
					drop: 4,
				})
			}
			if (this.stats.disk_used_pct !== null) {
				parts.push({
					icon: 'mdi-harddisk',
					label: this.$t('misc.footer.diskLabel'),
					text: this.$t('misc.footer.pct', {pct: this.stats.disk_used_pct}),
					color: this.severityColor(this.stats.disk_used_pct),
					drop: 3,
				})
			}
			return parts
		},
		visibleTextParts() {
			return this.textParts.filter((part) => !part.drop || part.drop > this.hideLevel)
		},
		visibleStatParts() {
			return this.statParts.filter((part) => !part.drop || part.drop > this.hideLevel)
		},
	},
	methods: {
		severityColor(pct, warnAt = 80, errorAt = 90) {
			// the theme's error/warning swatches are tuned to pop as fills
			// against a dark surface (or pair with on-error/on-warning text);
			// used as plain text on the light theme's white background they
			// fail contrast (warning #FFC107 is ~1.6:1 - near invisible), so
			// light mode gets darker, WCAG-AA-legible stand-ins here instead
			const dark = this.$vuetify.theme.global.current.dark
			if (pct > errorAt) return dark ? '#FF5252' : '#C62828'
			if (pct > warnAt) return dark ? '#FFC107' : '#E65100'
			return null
		},
		async refresh() {
			const res = await fetch('/api/system-info')
			if (res.ok) this.stats = await res.json()
			this.checkOverflow()
		},
		// drops segments (OS name, then HW name, then disk space, then
		// swap - see `drop` tiers in `textParts`/`statParts`) as soon as
		// the footer would wrap to a 3rd line, and reclaims them again
		// once there's room -
		// bounded in both directions (hideLevel only ranges 0..4), so this
		// can't loop forever regardless of viewport/content changes
		async checkOverflow() {
			await this.$nextTick()
			const el = this.$refs.footerText
			if (!el) return
			const lineHeight = parseFloat(getComputedStyle(el).lineHeight) || el.offsetHeight
			const lines = Math.round(el.scrollHeight / lineHeight)
			if (lines >= 3 && this.hideLevel < 4) {
				this.hideLevel++
				this.checkOverflow()
			} else if (lines <= 2 && this.hideLevel > 0) {
				this.hideLevel--
				await this.$nextTick()
				if (Math.round(el.scrollHeight / lineHeight) >= 3) this.hideLevel++
			}
		},
		onResize() {
			window.clearTimeout(this._resizeDebounce)
			this._resizeDebounce = window.setTimeout(this.checkOverflow, 200)
		},
	},
	mounted() {
		this.refresh()
		this._interval = window.setInterval(this.refresh, 10000)
		window.addEventListener('resize', this.onResize)
	},
	unmounted() {
		window.clearInterval(this._interval)
		window.clearTimeout(this._resizeDebounce)
		window.removeEventListener('resize', this.onResize)
	},
};

export {AppFooComp};

// vim: set noet ts=4 sw=4:
