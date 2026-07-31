import { buildSearchActionSchema } from "./searchAction";
import type { JsonLdObject, SearchActionInput } from "./types";
import { compactJsonLd } from "./utils";

export interface WebSiteSchemaInput {
  readonly id?: string;
  readonly name: string;
  readonly url: string;
  readonly searchAction?: SearchActionInput;
  readonly publisherId?: string;
}

/**
 * Builds WebSite schema with optional SearchAction support.
 */
export function buildWebSiteSchema(input: WebSiteSchemaInput): JsonLdObject {
  return compactJsonLd({
    "@type": "WebSite",
    "@id": input.id,
    name: input.name,
    url: input.url,
    publisher: input.publisherId ? { "@id": input.publisherId } : undefined,
    potentialAction: input.searchAction ? buildSearchActionSchema(input.searchAction) : undefined,
  });
}
