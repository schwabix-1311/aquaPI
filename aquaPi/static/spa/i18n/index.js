import de from './locales/de.js';
import en from './locales/en.js';
export default new VueI18n({
  locale: navigator.language.substr(0, 2) || 'en',
  fallbackLocale: 'de',
  messages: { de, en },
});