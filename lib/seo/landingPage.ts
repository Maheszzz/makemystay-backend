import type { Metadata } from "next";
import { buildBreadcrumbs, type BreadcrumbItem } from "./breadcrumbs";
import { generateSeoFaqs, type FaqItem } from "./faq";
import {
  type InternalLink,
  createInternalLink,
  normalizeInternalPath,
  selectInternalLinks,
} from "./internalLinks";
import {
  type LocalityContentInput,
  type LocalityContentResult,
  generateLocalityContent,
} from "./localityContent";
import { buildCanonicalUrl, buildMetadata, type SeoDefaults } from "./metadata";
import { generateSchema, type GenerateSchemaInput, type JsonLdObject } from "./schema";

export interface LandingPageLocation {
  readonly name: string;
  readonly slug?: string;
  readonly locality?: string;
  readonly city: string;
  readonly type?: "tech-park" | "business-park" | "landmark" | "metro" | "college" | "hospital" | "area";
  readonly latitude?: number;
  readonly longitude?: number;
}

export interface LandingPageGeneratorInput {
  readonly propertyType: string;
  readonly location: LandingPageLocation;
  readonly basePath?: string;
  readonly brandName?: string;
  readonly amenities?: readonly string[];
  readonly rent?: string | number;
  readonly rentRange?: string;
  readonly internalLinks?: readonly InternalLink[];
  readonly relatedLocations?: readonly LandingPageLocation[];
  readonly reviews?: LocalityContentInput["reviews"];
  readonly faqs?: readonly FaqItem[];
  readonly image?: string;
  readonly noIndex?: boolean;
}

export interface LandingPageGeneratorOptions {
  readonly contentMinimumWords?: number;
  readonly faqCount?: number;
  readonly internalLinkLimit?: number;
  readonly homeLabel?: string;
}

export interface LandingPageResult {
  readonly slug: string;
  readonly path: string;
  readonly canonicalUrl: string;
  readonly metadata: Metadata;
  readonly schema: JsonLdObject;
  readonly faqs: readonly FaqItem[];
  readonly content: LocalityContentResult;
  readonly internalLinks: readonly InternalLink[];
  readonly breadcrumbs: readonly BreadcrumbItem[];
}

export interface DynamicLandingRouteParams {
  readonly slug: string;
}

/**
 * Converts landing page terms into stable URL slugs.
 */
export function createLandingPageSlug(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Builds the canonical path for a dynamic landing page route.
 */
export function buildLandingPagePath(slug: string, basePath = "/pg-near"): string {
  return normalizeInternalPath(`${basePath}/${slug}`);
}

/**
 * Builds the primary search keyword for a landing page.
 */
export function buildLandingPageKeyword(propertyType: string, locationName: string): string {
  return `${propertyType.trim()} near ${locationName.trim()}`;
}

/**
 * Builds SEO keywords for near-me and landmark landing pages.
 */
export function buildLandingPageKeywords(input: LandingPageGeneratorInput): string[] {
  const keyword = buildLandingPageKeyword(input.propertyType, input.location.name);
  const locality = input.location.locality;
  const city = input.location.city;

  return [
    keyword,
    `best ${keyword}`,
    `luxury ${keyword}`,
    `affordable ${keyword}`,
    `verified ${keyword}`,
    `${keyword} ${city}`,
    locality ? `${input.propertyType} in ${locality}` : "",
    locality ? `${keyword} ${locality}` : "",
    ...(input.amenities ?? []).map((amenity) => `${keyword} with ${amenity}`),
  ].filter(Boolean);
}

/**
 * Builds landing page metadata for App Router generateMetadata usage.
 */
export function buildLandingPageMetadata(input: LandingPageGeneratorInput, defaults: SeoDefaults): Metadata {
  const slug = input.location.slug ?? createLandingPageSlug(input.location.name);
  const path = buildLandingPagePath(slug, input.basePath);
  const keyword = buildLandingPageKeyword(input.propertyType, input.location.name);
  const cityLabel = input.location.locality ? `${input.location.locality}, ${input.location.city}` : input.location.city;
  const description = `Find verified ${keyword} in ${cityLabel}. Compare rent, amenities, commute, reviews, availability and move-in ready stays on ${input.brandName ?? defaults.siteName}.`;

  return buildMetadata(
    {
      title: `${keyword} | ${cityLabel}`,
      description,
      path,
      image: input.image,
      keywords: buildLandingPageKeywords(input),
      locations: [input.location.name, input.location.locality ?? "", input.location.city].filter(Boolean),
      noIndex: input.noIndex,
    },
    defaults,
  );
}

/**
 * Builds structured content input for near-location landing pages.
 */
export function buildLandingPageContentInput(input: LandingPageGeneratorInput): LocalityContentInput {
  const keyword = buildLandingPageKeyword(input.propertyType, input.location.name);
  const locality = input.location.locality ?? input.location.name;

  return {
    locality,
    city: input.location.city,
    propertyType: input.propertyType,
    primaryKeyword: keyword,
    secondaryKeywords: buildLandingPageKeywords(input),
    amenities: input.amenities,
    rent: input.rent,
    rentRange: input.rentRange,
    techParks:
      input.location.type === "tech-park" || input.location.type === "business-park"
        ? [{ name: input.location.name }]
        : undefined,
    metroStations: input.location.type === "metro" ? [{ name: input.location.name }] : undefined,
    hospitals: input.location.type === "hospital" ? [{ name: input.location.name }] : undefined,
    colleges: input.location.type === "college" ? [{ name: input.location.name }] : undefined,
    nearbyAreas: input.relatedLocations?.map((location) => ({ name: location.name })),
    idealFor: ["working professionals", "students", "new city movers"],
    reviews: input.reviews,
    faqs: input.faqs,
    brandName: input.brandName,
  };
}

/**
 * Builds reusable FAQ data for a landing page.
 */
export function buildLandingPageFaqs(input: LandingPageGeneratorInput, faqCount = 15): FaqItem[] {
  if (input.faqs?.length) {
    return input.faqs.slice(0, faqCount);
  }

  return generateSeoFaqs(
    {
      locality: input.location.name,
      city: input.location.city,
      propertyType: input.propertyType,
      amenities: input.amenities,
      rent: input.rentRange ?? input.rent,
      brandName: input.brandName,
    },
    { count: faqCount },
  );
}

/**
 * Builds internal links for the current landing page from supplied links and related locations.
 */
export function buildLandingPageInternalLinks(
  input: LandingPageGeneratorInput,
  currentPath: string,
  limit = 12,
): InternalLink[] {
  const relatedLinks = (input.relatedLocations ?? []).map((location) =>
    createInternalLink(
      buildLandingPageKeyword(input.propertyType, location.name),
      buildLandingPagePath(location.slug ?? createLandingPageSlug(location.name), input.basePath),
      {
        priority: 50,
        tags: ["landing", "nearby", location.type ?? "location"],
      },
    ),
  );

  return selectInternalLinks([...(input.internalLinks ?? []), ...relatedLinks], {
    currentPath,
    tags: ["landing", "nearby", input.location.type ?? "location"],
    limit,
  });
}

/**
 * Builds JSON-LD schema for a landing page using WebSite, WebPage, Place, Breadcrumb and FAQ data.
 */
export function buildLandingPageSchema(
  input: LandingPageGeneratorInput,
  defaults: SeoDefaults,
  path: string,
  breadcrumbs: readonly BreadcrumbItem[],
  faqs: readonly FaqItem[],
): JsonLdObject {
  const canonicalUrl = buildCanonicalUrl(defaults.baseUrl, path);
  const keyword = buildLandingPageKeyword(input.propertyType, input.location.name);
  const schemaInput: GenerateSchemaInput = {
    organization: {
      name: defaults.siteName,
      url: defaults.baseUrl,
      logo: defaults.defaultImage,
    },
    webSite: {
      name: defaults.siteName,
      url: defaults.baseUrl,
      searchAction: {
        target: `${defaults.baseUrl.replace(/\/+$/, "")}/search?q={search_term_string}`,
      },
    },
    webPage: {
      name: keyword,
      url: canonicalUrl,
      description: `Verified ${keyword} with rent, amenities, commute, FAQs and nearby stay options.`,
      image: input.image ?? defaults.defaultImage,
    },
    place: {
      name: input.location.name,
      url: canonicalUrl,
      description: `${input.location.name} is a demand center for ${input.propertyType} accommodation in ${input.location.city}.`,
      geo:
        input.location.latitude !== undefined && input.location.longitude !== undefined
          ? {
              latitude: input.location.latitude,
              longitude: input.location.longitude,
            }
          : undefined,
      address: {
        addressLocality: input.location.locality ?? input.location.name,
        addressRegion: input.location.city,
        addressCountry: "IN",
      },
    },
    breadcrumb: breadcrumbs,
    faq: faqs,
  };

  return generateSchema(schemaInput);
}

/**
 * Generates every SEO artifact needed by a dynamic landing page.
 */
export function generateLandingPage(
  input: LandingPageGeneratorInput,
  defaults: SeoDefaults,
  options: LandingPageGeneratorOptions = {},
): LandingPageResult {
  const slug = input.location.slug ?? createLandingPageSlug(input.location.name);
  const path = buildLandingPagePath(slug, input.basePath);
  const canonicalUrl = buildCanonicalUrl(defaults.baseUrl, path);
  const metadata = buildLandingPageMetadata(input, defaults);
  const faqs = buildLandingPageFaqs(input, options.faqCount ?? 15);
  const content = generateLocalityContent(
    {
      ...buildLandingPageContentInput(input),
      faqs,
    },
    {
      minimumWords: options.contentMinimumWords ?? 2000,
      faqCount: options.faqCount ?? 15,
    },
  );
  const internalLinks = buildLandingPageInternalLinks(input, path, options.internalLinkLimit ?? 12);
  const breadcrumbs = buildBreadcrumbs(path, {
    baseUrl: defaults.baseUrl,
    homeLabel: options.homeLabel ?? "Home",
    labels: {
      [slug]: buildLandingPageKeyword(input.propertyType, input.location.name),
    },
  });
  const schema = buildLandingPageSchema(input, defaults, path, breadcrumbs, faqs);

  return {
    slug,
    path,
    canonicalUrl,
    metadata,
    schema,
    faqs,
    content,
    internalLinks,
    breadcrumbs,
  };
}

/**
 * Converts landing page locations into Next.js generateStaticParams output.
 */
export function generateLandingPageStaticParams(locations: readonly LandingPageLocation[]): DynamicLandingRouteParams[] {
  return locations.map((location) => ({
    slug: location.slug ?? createLandingPageSlug(location.name),
  }));
}

/**
 * Finds landing page data from dynamic route params.
 */
export function findLandingPageByParams(
  params: DynamicLandingRouteParams,
  locations: readonly LandingPageLocation[],
): LandingPageLocation | undefined {
  return locations.find((location) => (location.slug ?? createLandingPageSlug(location.name)) === params.slug);
}

/**
 * Creates a reusable App Router generateMetadata function for landing page dynamic routes.
 */
export function createLandingPageGenerateMetadata(
  locations: readonly LandingPageLocation[],
  defaults: SeoDefaults,
  inputFactory: (location: LandingPageLocation) => Omit<LandingPageGeneratorInput, "location">,
) {
  return async function generateMetadata({ params }: { params: DynamicLandingRouteParams }): Promise<Metadata> {
    const location = findLandingPageByParams(params, locations);

    if (!location) {
      return buildMetadata(
        {
          title: "Page not found",
          description: defaults.defaultDescription,
          noIndex: true,
        },
        defaults,
      );
    }

    return buildLandingPageMetadata(
      {
        ...inputFactory(location),
        location,
      },
      defaults,
    );
  };
}
