// Tests switch to English by setting lang.value = 'en' (docs/i18n.md); in the app the English is loaded at start-up only
// in English mode, so load it here up front. Chinese stays the default: t() ignores the dictionaries in Chinese mode.
import { loadLanguage } from '@/i18n'

await loadLanguage(true)
