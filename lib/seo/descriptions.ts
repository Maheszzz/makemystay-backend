export interface DescriptionOptions {
  readonly fallback?: string;
  readonly minLength?: number;
  readonly maxLength?: number;
}

const DEFAULT_DESCRIPTION_MIN_LENGTH = 70;
const DEFAULT_DESCRIPTION_MAX_LENGTH = 155;

/**
 * Normalizes whitespace in a meta description and removes surrounding punctuation noise.
 */
export function normalizeDescription(description: string): string {
  return description.replace(/\s+/g, " ").trim().replace(/\s+([,.!?;:])/g, "$1");
}

/**
 * Truncates a description at a word boundary to reduce awkward SERP snippets.
 */
export function truncateDescription(description: string, maxLength = DEFAULT_DESCRIPTION_MAX_LENGTH): string {
  const normalizedDescription = normalizeDescription(description);

  if (normalizedDescription.length <= maxLength) {
    return normalizedDescription;
  }

  const shortened = normalizedDescription.slice(0, Math.max(0, maxLength - 1)).trimEnd();
  const lastSpace = shortened.lastIndexOf(" ");

  if (lastSpace > Math.floor(maxLength * 0.7)) {
    return `${shortened.slice(0, lastSpace)}...`;
  }

  return `${shortened}...`;
}

/**
 * Returns true when a description is long enough to be useful as metadata.
 */
export function hasUsefulDescription(description: string, minLength = DEFAULT_DESCRIPTION_MIN_LENGTH): boolean {
  return normalizeDescription(description).length >= minLength;
}

/**
 * Builds a meta description with fallback handling and SEO-friendly length constraints.
 */
export function buildDescription(description: string | null | undefined, options: DescriptionOptions = {}): string {
  const source = description && hasUsefulDescription(description, options.minLength) ? description : options.fallback ?? description ?? "";

  return truncateDescription(source, options.maxLength ?? DEFAULT_DESCRIPTION_MAX_LENGTH);
}
