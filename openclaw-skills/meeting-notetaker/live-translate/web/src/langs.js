// Target languages offered in the UI. Codes match translator.py's lang_name().
export const LANGS = [
  { code: "vi", label: "Tiếng Việt" },
  { code: "en", label: "English" },
  { code: "ja", label: "日本語" },
  { code: "ko", label: "한국어" },
  { code: "zh", label: "中文" },
  { code: "fr", label: "Français" },
  { code: "de", label: "Deutsch" },
  { code: "es", label: "Español" },
  { code: "th", label: "ไทย" },
  { code: "id", label: "Indonesia" },
];

export function labelFor(code) {
  return LANGS.find((l) => l.code === code)?.label || code;
}
