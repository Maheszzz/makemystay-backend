export interface TitleOptions {
  readonly template?: string;
  readonly suffix?: string;
  readonly maxLength?: number;
}

const DEFAULT_TITLE_MAX_LENGTH = 60;

/**
 * Normalizes whitespace in title text so generated metadata stays readable and stable.
 */
export function normalizeTitle(title: string): string {
  return title.replace(/\s+/g, " ").trim();
}

/**
 * Appends a brand suffix to a title unless the suffix is already present.
 */
export function appendTitleSuffix(title: string, suffix = "MakeMyStay"): string {
  const normalizedTitle = normalizeTitle(title);
  const normalizedSuffix = normalizeTitle(suffix);

  if (!normalizedTitle || !normalizedSuffix) {
    return normalizedTitle || normalizedSuffix;
  }

  if (normalizedTitle.toLowerCase().endsWith(normalizedSuffix.toLowerCase())) {
    return normalizedTitle;
  }

  return `${normalizedTitle} | ${normalizedSuffix}`;
}

/**
 * Applies a title template containing `%s` and falls back to the raw title if no template is provided.
 */
export function applyTitleTemplate(title: string, template?: string): string {
  const normalizedTitle = normalizeTitle(title);

  if (!template) {
    return normalizedTitle;
  }

  return normalizeTitle(template.replace("%s", normalizedTitle));
}

/**
 * Truncates a title at a word boundary where possible to keep SERP titles concise.
 */
export function truncateTitle(title: string, maxLength = DEFAULT_TITLE_MAX_LENGTH): string {
  const normalizedTitle = normalizeTitle(title);

  if (normalizedTitle.length <= maxLength) {
    return normalizedTitle;
  }

  const shortened = normalizedTitle.slice(0, Math.max(0, maxLength - 1)).trimEnd();
  const lastSpace = shortened.lastIndexOf(" ");

  if (lastSpace > Math.floor(maxLength * 0.6)) {
    return `${shortened.slice(0, lastSpace)}...`;
  }

  return `${shortened}...`;
}

/**
 * Builds a production-ready title from reusable options without coupling to a specific page.
 */
export function buildTitle(title: string, options: TitleOptions = {}): string {
  const withTemplate = applyTitleTemplate(title, options.template);
  const withSuffix = options.suffix ? appendTitleSuffix(withTemplate, options.suffix) : withTemplate;

  return truncateTitle(withSuffix, options.maxLength ?? DEFAULT_TITLE_MAX_LENGTH);
}
