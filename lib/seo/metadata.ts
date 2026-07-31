import type { Metadata } from "next";
import { buildDescription } from "./descriptions";
import { normalizeInternalPath } from "./internalLinks";
import { buildKeywords } from "./keywords";
import { buildTitle } from "./titles";

export type SeoEntityType = "property" | "locality";

export interface AlternateUrl {
  readonly hrefLang: string;
  readonly path: string;
}

export interface SeoMetadataInput {
  readonly title: string;
  readonly description?: string | null;
  readonly path?: string;
  readonly siteName?: string;
  readonly baseUrl?: string;
  readonly image?: string | readonly string[];
  readonly keywords?: readonly string[];
  readonly locations?: readonly string[];
  readonly noIndex?: boolean;
  readonly type?: "website" | "article";
  readonly publishedTime?: string;
  readonly modifiedTime?: string;
  readonly alternates?: readonly AlternateUrl[];
}

export interface SeoDefaults {
  readonly siteName: string;
  readonly baseUrl: string;
  readonly titleSuffix?: string;
  readonly defaultDescription: string;
  readonly defaultImage?: string;
  readonly defaultKeywords?: readonly string[];
  readonly locale?: string;
  readonly twitterSite?: string;
}

export interface PropertyMetadataInput {
  readonly type: "property";
  readonly name: string;
  readonly locality: string;
  readonly city: string;
  readonly slug: string;
  readonly titleQualifier?: string;
  readonly description?: string | null;
  readonly propertyType?: string;
  readonly priceLabel?: string;
  readonly amenities?: readonly string[];
  readonly images?: readonly string[];
  readonly noIndex?: boolean;
  readonly alternateUrls?: readonly AlternateUrl[];
}

export interface LocalityMetadataInput {
  readonly type: "locality";
  readonly locality: string;
  readonly city: string;
  readonly slug: string;
  readonly titleQualifier?: string;
  readonly description?: string | null;
  readonly primaryKeyword: string;
  readonly keywords?: readonly string[];
  readonly nearbyPlaces?: readonly string[];
  readonly image?: string;
  readonly noIndex?: boolean;
  readonly alternateUrls?: readonly AlternateUrl[];
}

export type EntityMetadataInput = PropertyMetadataInput | LocalityMetadataInput;

export interface EntityMetadataOptions {
  readonly propertyBasePath?: string;
  readonly localityBasePath?: string;
}

/**
 * Converts a relative path into an absolute URL using the configured site origin.
 */
export function buildCanonicalUrl(baseUrl: string, path = "/"): string {
  return new URL(normalizeInternalPath(path), baseUrl).toString();
}

/**
 * Normalizes Open Graph image input into the shape expected by Next.js metadata.
 */
export function buildOpenGraphImages(image?: string | readonly string[], fallbackImage?: string): NonNullable<Metadata["openGraph"]>["images"] {
  const images = Array.isArray(image) ? image : image ? [image] : fallbackImage ? [fallbackImage] : [];

  return images.map((url) => ({ url }));
}

/**
 * Builds robots metadata from a noIndex flag while keeping follow behavior explicit.
 */
export function buildRobots(noIndex = false): Metadata["robots"] {
  return {
    index: !noIndex,
    follow: !noIndex,
    googleBot: {
      index: !noIndex,
      follow: !noIndex,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  };
}

/**
 * Builds alternate language URLs in the format expected by Next.js metadata.
 */
export function buildAlternateLanguages(
  baseUrl: string,
  alternates: readonly AlternateUrl[] = [],
): NonNullable<NonNullable<Metadata["alternates"]>["languages"]> | undefined {
  if (alternates.length === 0) {
    return undefined;
  }

  return alternates.reduce<Record<string, string>>((languages, alternate) => {
    languages[alternate.hrefLang] = buildCanonicalUrl(baseUrl, alternate.path);

    return languages;
  }, {});
}

/**
 * Builds a stable property route from a slug and configurable base path.
 */
export function buildPropertyPath(slug: string, basePath = "/properties"): string {
  return normalizeInternalPath(`${basePath}/${slug}`);
}

/**
 * Builds a stable locality route from a slug and configurable base path.
 */
export function buildLocalityPath(slug: string, basePath = "/pg"): string {
  return normalizeInternalPath(`${basePath}/${slug}`);
}

/**
 * Builds a unique property title using the property name, locality, and city.
 */
export function buildPropertyTitle(input: PropertyMetadataInput): string {
  const typeLabel = input.propertyType ? `${input.propertyType} ` : "";
  const qualifier = input.titleQualifier ? ` ${input.titleQualifier}` : "";

  return `${input.name}${qualifier} | ${typeLabel}PG in ${input.locality}, ${input.city}`;
}

/**
 * Builds a unique locality title from the locality primary keyword and city.
 */
export function buildLocalityTitle(input: LocalityMetadataInput): string {
  const qualifier = input.titleQualifier ? ` ${input.titleQualifier}` : "";

  return `${input.primaryKeyword}${qualifier} | ${input.locality}, ${input.city}`;
}

/**
 * Builds a property description with useful commercial and location context.
 */
export function buildPropertyDescription(input: PropertyMetadataInput): string {
  if (input.description) {
    return input.description;
  }

  const amenityText = input.amenities?.length ? ` with ${input.amenities.slice(0, 3).join(", ")}` : "";
  const priceText = input.priceLabel ? ` from ${input.priceLabel}` : "";

  return `Explore ${input.name}, a verified PG in ${input.locality}, ${input.city}${amenityText}${priceText}. Check rooms, amenities, location, and availability on MakeMyStay.`;
}

/**
 * Builds a locality description with primary keyword, nearby context, and booking intent.
 */
export function buildLocalityDescription(input: LocalityMetadataInput): string {
  if (input.description) {
    return input.description;
  }

  const nearbyText = input.nearbyPlaces?.length ? ` near ${input.nearbyPlaces.slice(0, 3).join(", ")}` : "";

  return `Find verified ${input.primaryKeyword}${nearbyText}. Compare furnished PGs, coliving spaces, amenities, rent, and move-in options in ${input.locality}, ${input.city}.`;
}

/**
 * Builds keyword phrases for a property without duplicating title-only logic.
 */
export function buildPropertyKeywords(input: PropertyMetadataInput): string[] {
  return [
    input.name,
    `PG in ${input.locality}`,
    `PG in ${input.locality} ${input.city}`,
    input.propertyType ? `${input.propertyType} PG in ${input.locality}` : "",
    ...(input.amenities ?? []).map((amenity) => `PG in ${input.locality} with ${amenity}`),
  ].filter(Boolean);
}

/**
 * Converts a property or locality SEO entity into reusable page-neutral metadata input.
 */
export function buildEntityMetadataInput(
  input: EntityMetadataInput,
  options: EntityMetadataOptions = {},
): SeoMetadataInput {
  if (input.type === "property") {
    return {
      title: buildPropertyTitle(input),
      description: buildPropertyDescription(input),
      path: buildPropertyPath(input.slug, options.propertyBasePath),
      image: input.images,
      keywords: buildPropertyKeywords(input),
      locations: [input.locality, input.city],
      noIndex: input.noIndex,
      alternates: input.alternateUrls,
    };
  }

  return {
    title: buildLocalityTitle(input),
    description: buildLocalityDescription(input),
    path: buildLocalityPath(input.slug, options.localityBasePath),
    image: input.image,
    keywords: input.keywords,
    locations: [input.locality, input.city],
    noIndex: input.noIndex,
    alternates: input.alternateUrls,
  };
}

/**
 * Builds reusable Next.js App Router metadata from page-neutral SEO inputs and site defaults.
 */
export function buildMetadata(input: SeoMetadataInput, defaults: SeoDefaults): Metadata {
  const siteName = input.siteName ?? defaults.siteName;
  const baseUrl = input.baseUrl ?? defaults.baseUrl;
  const canonicalUrl = buildCanonicalUrl(baseUrl, input.path);
  const title = buildTitle(input.title, { suffix: defaults.titleSuffix ?? siteName });
  const description = buildDescription(input.description, { fallback: defaults.defaultDescription });
  const images = buildOpenGraphImages(input.image, defaults.defaultImage);
  const keywords = buildKeywords(defaults.defaultKeywords ?? [], input.locations ?? [], input.keywords ?? [], {
    includeLocationVariants: Boolean(input.locations?.length),
  });
  const languages = buildAlternateLanguages(baseUrl, input.alternates);
  const alternates: NonNullable<Metadata["alternates"]> = languages
    ? {
        canonical: canonicalUrl,
        languages,
      }
    : {
        canonical: canonicalUrl,
      };
  const openGraph: NonNullable<Metadata["openGraph"]> =
    input.type === "article"
      ? {
          title,
          description,
          url: canonicalUrl,
          siteName,
          images,
          type: "article",
          locale: defaults.locale ?? "en_IN",
          publishedTime: input.publishedTime,
          modifiedTime: input.modifiedTime,
        }
      : {
          title,
          description,
          url: canonicalUrl,
          siteName,
          images,
          type: "website",
          locale: defaults.locale ?? "en_IN",
        };

  return {
    title,
    description,
    keywords,
    alternates,
    robots: buildRobots(input.noIndex),
    openGraph,
    twitter: {
      card: images.length > 0 ? "summary_large_image" : "summary",
      title,
      description,
      images: images.map((item) => item.url),
      site: defaults.twitterSite,
    },
  };
}

/**
 * Builds complete metadata for a property or locality entity.
 */
export function buildEntityMetadata(
  input: EntityMetadataInput,
  defaults: SeoDefaults,
  options: EntityMetadataOptions = {},
): Metadata {
  return buildMetadata(buildEntityMetadataInput(input, options), defaults);
}

/**
 * Returns duplicate metadata titles for a collection of SEO entities after final title normalization.
 */
export function findDuplicateMetadataTitles(
  inputs: readonly EntityMetadataInput[],
  defaults: SeoDefaults,
  options: EntityMetadataOptions = {},
): string[] {
  const seen = new Set<string>();
  const duplicates = new Set<string>();

  for (const input of inputs) {
    const metadataInput = buildEntityMetadataInput(input, options);
    const title = buildTitle(metadataInput.title, { suffix: defaults.titleSuffix ?? defaults.siteName }).toLowerCase();

    if (seen.has(title)) {
      duplicates.add(title);
    }

    seen.add(title);
  }

  return [...duplicates];
}

/**
 * Creates a Next.js App Router generateMetadata function from reusable entity loading logic.
 */
export function createGenerateMetadata<TParams extends Record<string, string | string[] | undefined>>(
  loadEntity: (params: TParams) => Promise<EntityMetadataInput | null> | EntityMetadataInput | null,
  defaults: SeoDefaults,
  options: EntityMetadataOptions = {},
) {
  return async function generateMetadata({ params }: { params: TParams }): Promise<Metadata> {
    const entity = await loadEntity(params);

    if (!entity) {
      return buildMetadata(
        {
          title: "Page not found",
          description: defaults.defaultDescription,
          noIndex: true,
        },
        defaults,
      );
    }

    return buildEntityMetadata(entity, defaults, options);
  };
}
