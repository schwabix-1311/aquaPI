// Resolves a POST /api/config/apply failure into a localized message.
// The backend (db.ConfigDiffError, see aquaPi/db.py) always returns a
// plain-English `error` string as a guaranteed fallback, and optionally
// `error_key`/`error_params` (one translatable message) or `error_items`
// (a list of independent violations, e.g. several nodes each missing a
// required value/connection) for messages that have been migrated to
// pages.wiring.errors.<key> - not yet all of them, so falling back to
// the raw `error` string when neither is present is expected, not a bug.
//
// `result` is the {ok, error, errorKey, errorParams, errorItems} shape
// the wiring store's actions return (apiRequest's snake_case JSON body
// mapped to camelCase - see store/modules/wiring.js).

export function resolveConfigDiffError(result, t) {
	if (result.errorItems && result.errorItems.length) {
		return result.errorItems.map(({key, params}) => {
			// 'missingValue's fieldLabel is itself an i18n key (reusing
			// pages.settings.fields.*, e.g. 'inputPort'/'setpoint') -
			// resolve it first, then interpolate the resolved text.
			const p = (key === 'missingValue' && params && params.fieldLabel)
				? {...params, fieldLabel: t('pages.settings.fields.' + params.fieldLabel)}
				: params
			return t('pages.wiring.errors.' + key, p)
		}).join('; ')
	}
	if (result.errorKey) {
		return t('pages.wiring.errors.' + result.errorKey, result.errorParams)
	}
	return result.error
}

// vim: set noet ts=4 sw=4:
