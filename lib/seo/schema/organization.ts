import type { JsonLdObject } from "./types";
import { compactJsonLd } from "./utils";

export interface OrganizationSchemaInput {
  readonly id?: string;
  readonly name: string;
  readonly url: string;
  readonly logo?: string;
  readonly sameAs?: readonly string[];
  readonly contactPoint?: JsonLdObject | readonly JsonLdObject[];
}

/**
 * Builds Organization schema for the MakeMyStay brand or another reusable organization entity.
 */
export function buildOrganizationSchema(input: OrganizationSchemaInput): JsonLdObject {
  return compactJsonLd({
    "@type": "Organization",
    "@id": input.id,
    name: input.name,
    url: input.url,
    logo: input.logo,
    sameAs: input.sameAs,
    contactPoint: input.contactPoint,
  });
}
