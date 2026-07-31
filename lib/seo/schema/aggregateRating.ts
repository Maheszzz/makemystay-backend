import type { AggregateRatingInput, JsonLdObject } from "./types";
import { compactJsonLd } from "./utils";

/**
 * Builds AggregateRating schema using review count and normalized rating bounds.
 */
export function buildAggregateRatingSchema(input: AggregateRatingInput): JsonLdObject {
  return compactJsonLd({
    "@type": "AggregateRating",
    ratingValue: input.ratingValue,
    reviewCount: input.reviewCount,
    bestRating: input.bestRating ?? 5,
    worstRating: input.worstRating ?? 1,
  });
}
