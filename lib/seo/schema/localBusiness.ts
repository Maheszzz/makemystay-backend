import { buildAggregateRatingSchema } from "./aggregateRating";
import { buildGeoCoordinatesSchema } from "./geoCoordinates";
import type { AggregateRatingInput, GeoCoordinatesInput, JsonLdObject, OpeningHoursInput, PostalAddressInput } from "./types";
import { compactJsonLd } from "./utils";

export interface LocalBusinessSchemaInput {
  readonly id?: string;
  readonly name: string;
  readonly url: string;
  readonly image?: string | readonly string[];
  readonly telephone?: string;
  readonly priceRange?: string;
  readonly address?: PostalAddressInput;
  readonly geo?: GeoCoordinatesInput;
  readonly openingHoursSpecification?: readonly OpeningHoursInput[];
  readonly aggregateRating?: AggregateRatingInput;
}

/**
 * Builds LocalBusiness schema for a location, property operator, or branch.
 */
export function buildLocalBusinessSchema(input: LocalBusinessSchemaInput): JsonLdObject {
  return compactJsonLd({
    "@type": "LocalBusiness",
    "@id": input.id,
    name: input.name,
    url: input.url,
    image: input.image,
    telephone: input.telephone,
    priceRange: input.priceRange,
    address: input.address
      ? {
          "@type": "PostalAddress",
          ...input.address,
        }
      : undefined,
    geo: input.geo ? buildGeoCoordinatesSchema(input.geo) : undefined,
    openingHoursSpecification: input.openingHoursSpecification?.map((hours) => ({
      "@type": "OpeningHoursSpecification",
      dayOfWeek: hours.dayOfWeek,
      opens: hours.opens,
      closes: hours.closes,
    })),
    aggregateRating: input.aggregateRating ? buildAggregateRatingSchema(input.aggregateRating) : undefined,
  });
}
