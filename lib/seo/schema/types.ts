export type JsonLdScalar = string | number | boolean | null | undefined;

export type JsonLdValue = JsonLdScalar | JsonLdObject | readonly JsonLdValue[];

export interface JsonLdObject {
  readonly [key: string]: JsonLdValue;
}

export interface PostalAddressInput {
  readonly streetAddress?: string;
  readonly addressLocality?: string;
  readonly addressRegion?: string;
  readonly postalCode?: string;
  readonly addressCountry?: string;
}

export interface GeoCoordinatesInput {
  readonly latitude: number;
  readonly longitude: number;
}

export interface AggregateRatingInput {
  readonly ratingValue: number;
  readonly reviewCount: number;
  readonly bestRating?: number;
  readonly worstRating?: number;
}

export interface OpeningHoursInput {
  readonly dayOfWeek: readonly string[];
  readonly opens: string;
  readonly closes: string;
}

export interface BreadcrumbSchemaItem {
  readonly name: string;
  readonly href: string;
}

export interface FaqSchemaItem {
  readonly question: string;
  readonly answer: string;
}

export interface SearchActionInput {
  readonly target: string;
  readonly queryInput?: string;
}

export interface SchemaEntityReference {
  readonly id?: string;
  readonly name?: string;
  readonly url?: string;
}
