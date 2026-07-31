import { buildAggregateRatingSchema } from "./aggregateRating";
import { buildGeoCoordinatesSchema } from "./geoCoordinates";
import type { AggregateRatingInput, GeoCoordinatesInput, JsonLdObject, PostalAddressInput } from "./types";
import { compactJsonLd } from "./utils";

export interface PlaceSchemaInput {
  readonly id?: string;
  readonly name: string;
  readonly url?: string;
  readonly description?: string;
  readonly image?: string | readonly string[];
  readonly address?: PostalAddressInput;
  readonly geo?: GeoCoordinatesInput;
  readonly aggregateRating?: AggregateRatingInput;
}

/**
 * Builds Place schema for localities, landmarks, campuses, or neighborhood pages.
 */
export function buildPlaceSchema(input: PlaceSchemaInput): JsonLdObject {
  return compactJsonLd({
    "@type": "Place",
    "@id": input.id,
    name: input.name,
    url: input.url,
    description: input.description,
    image: input.image,
    address: input.address
      ? {
          "@type": "PostalAddress",
          ...input.address,
        }
      : undefined,
    geo: input.geo ? buildGeoCoordinatesSchema(input.geo) : undefined,
    aggregateRating: input.aggregateRating ? buildAggregateRatingSchema(input.aggregateRating) : undefined,
  });
}
