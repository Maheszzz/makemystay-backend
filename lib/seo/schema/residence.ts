import { buildAggregateRatingSchema } from "./aggregateRating";
import { buildGeoCoordinatesSchema } from "./geoCoordinates";
import type { AggregateRatingInput, GeoCoordinatesInput, JsonLdObject, PostalAddressInput } from "./types";
import { compactJsonLd } from "./utils";

export interface ResidenceSchemaInput {
  readonly id?: string;
  readonly name: string;
  readonly url: string;
  readonly description?: string;
  readonly image?: string | readonly string[];
  readonly address?: PostalAddressInput;
  readonly geo?: GeoCoordinatesInput;
  readonly numberOfRooms?: number;
  readonly amenityFeature?: readonly string[];
  readonly aggregateRating?: AggregateRatingInput;
}

/**
 * Builds Residence schema for PG, coliving, apartment, or rental property pages.
 */
export function buildResidenceSchema(input: ResidenceSchemaInput): JsonLdObject {
  return compactJsonLd({
    "@type": "Residence",
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
    numberOfRooms: input.numberOfRooms,
    amenityFeature: input.amenityFeature?.map((amenity) => ({
      "@type": "LocationFeatureSpecification",
      name: amenity,
      value: true,
    })),
    aggregateRating: input.aggregateRating ? buildAggregateRatingSchema(input.aggregateRating) : undefined,
  });
}
