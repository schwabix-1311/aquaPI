import de from './locales/de.js';
import en from './locales/en.js';

const i18n = VueI18n.createI18n({
	legacy: false,
	globalInjection: true,
	locale: navigator.language.substring(0, 2) || 'en',
	fallbackLocale: 'de',
	messages: {de, en},
});

// window.__APP_NAME__ is set by spa.html.jinja2 from the backend's
// app.config['APP_NAME'] - overriding it here, once, at startup is the
// single place the brand name enters the SPA; everything else reads
// $t('app.name') or links to it via vue-i18n's '@:app.name' syntax
// (see pages.dashboard.heading/pages.about.* in the locale files).
if (window.__APP_NAME__) {
	for (const locale of Object.keys(i18n.global.messages.value)) {
		i18n.global.messages.value[locale].app.name = window.__APP_NAME__
	}
}

export default i18n;

// vim: set noet ts=4 sw=4:
