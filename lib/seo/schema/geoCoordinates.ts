import type { GeoCoordinatesInput, JsonLdObject } from "./types";
import { compactJsonLd } from "./utils";

/**
 * Builds GeoCoordinates schema for businesses, places, and residences.
 */
export function buildGeoCoordinatesSchema(input: GeoCoordinatesInput): JsonLdObject {
  return compactJsonLd({
    "@type": "GeoCoordinates",
    latitude: input.latitude,
    longitude: input.longitude,
  });
}
