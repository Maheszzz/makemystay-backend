import type { JsonLdObject } from "./types";
import { compactJsonLd } from "./utils";

export interface WebPageSchemaInput {
  readonly id?: string;
  readonly name: string;
  readonly url: string;
  readonly description?: string;
  readonly datePublished?: string;
  readonly dateModified?: string;
  readonly image?: string | readonly string[];
  readonly speakable?: JsonLdObject;
}

/**
 * Builds WebPage schema for indexable pages without page-specific branching.
 */
export function buildWebPageSchema(input: WebPageSchemaInput): JsonLdObject {
  return compactJsonLd({
    "@type": "WebPage",
    "@id": input.id,
    name: input.name,
    url: input.url,
    description: input.description,
    image: input.image,
    datePublished: input.datePublished,
    dateModified: input.dateModified,
    speakable: input.speakable,
  });
}
