import type { JsonLdObject } from "./types";
import { compactJsonLd } from "./utils";

export interface SpeakableSchemaInput {
  readonly cssSelector?: readonly string[];
  readonly xpath?: readonly string[];
}

/**
 * Builds SpeakableSpecification schema for clearly marked page excerpts.
 */
export function buildSpeakableSchema(input: SpeakableSchemaInput): JsonLdObject {
  return compactJsonLd({
    "@type": "SpeakableSpecification",
    cssSelector: input.cssSelector,
    xpath: input.xpath,
  });
}
