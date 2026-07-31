import type { JsonLdObject, SearchActionInput } from "./types";
import { compactJsonLd } from "./utils";

/**
 * Builds SearchAction schema for site search discovery in Google.
 */
export function buildSearchActionSchema(input: SearchActionInput): JsonLdObject {
  return compactJsonLd({
    "@type": "SearchAction",
    target: input.target,
    "query-input": input.queryInput ?? "required name=search_term_string",
  });
}
