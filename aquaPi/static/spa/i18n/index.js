import de from './locales/de.js';
import en from './locales/en.js';

export default VueI18n.createI18n({
	legacy: false,
	globalInjection: true,
	locale: navigator.language.substring(0, 2) || 'en',
	fallbackLocale: 'de',
	messages: {de, en},
});

// vim: set noet ts=4 sw=4:
