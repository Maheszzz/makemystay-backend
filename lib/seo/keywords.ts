export interface KeywordOptions {
  readonly maxKeywords?: number;
  readonly includeLocationVariants?: boolean;
}

const DEFAULT_MAX_KEYWORDS = 20;

/**
 * Converts arbitrary text into a lowercase keyword-safe phrase.
 */
export function normalizeKeyword(keyword: string): string {
  return keyword.replace(/\s+/g, " ").trim().toLowerCase();
}

/**
 * Removes empty and duplicate keywords while preserving the original order.
 */
export function uniqueKeywords(keywords: readonly string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  for (const keyword of keywords) {
    const normalizedKeyword = normalizeKeyword(keyword);

    if (!normalizedKeyword || seen.has(normalizedKeyword)) {
      continue;
    }

    seen.add(normalizedKeyword);
    result.push(normalizedKeyword);
  }

  return result;
}

/**
 * Creates location-aware keyword combinations from base topics and locations.
 */
export function buildLocationKeywords(baseKeywords: readonly string[], locations: readonly string[]): string[] {
  const combinations = baseKeywords.flatMap((keyword) =>
    locations.map((location) => `${normalizeKeyword(keyword)} in ${normalizeKeyword(location)}`),
  );

  return uniqueKeywords(combinations);
}

/**
 * Builds a reusable keyword set from core terms, optional locations, and optional custom terms.
 */
export function buildKeywords(
  baseKeywords: readonly string[],
  locations: readonly string[] = [],
  customKeywords: readonly string[] = [],
  options: KeywordOptions = {},
): string[] {
  const locationKeywords = options.includeLocationVariants === false ? [] : buildLocationKeywords(baseKeywords, locations);
  const keywords = uniqueKeywords([...baseKeywords, ...locationKeywords, ...customKeywords]);

  return keywords.slice(0, options.maxKeywords ?? DEFAULT_MAX_KEYWORDS);
}

/**
 * Serializes keywords for consumers that still require comma-separated meta keyword content.
 */
export function serializeKeywords(keywords: readonly string[]): string {
  return uniqueKeywords(keywords).join(", ");
}
