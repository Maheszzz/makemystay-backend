import type { MetadataRoute } from "next";
import { createBlogSlug, getBlogTopicTitle, type BlogGeneratorInput, type BlogTopic } from "./blogGenerator";
import { createLandingPageSlug, buildLandingPagePath, type LandingPageLocation } from "./landingPage";
import { buildCanonicalUrl } from "./metadata";

export type SitemapChangeFrequency = "always" | "hourly" | "daily" | "weekly" | "monthly" | "yearly" | "never";

export type SitemapPageType = "property" | "locality" | "blog" | "landing" | "static";

export interface SitemapImage {
  readonly url: string;
  readonly caption?: string;
  readonly title?: string;
  readonly geoLocation?: string;
  readonly license?: string;
}

export interface SitemapVideo {
  readonly thumbnailUrl: string;
  readonly title: string;
  readonly description: string;
  readonly contentUrl?: string;
  readonly playerUrl?: string;
  readonly durationSeconds?: number;
  readonly expirationDate?: string | Date;
  readonly publicationDate?: string | Date;
  readonly familyFriendly?: boolean;
  readonly live?: boolean;
  readonly tags?: readonly string[];
}

export interface SitemapSourceRecord {
  readonly slug: string;
  readonly updatedAt?: string | Date;
  readonly createdAt?: string | Date;
  readonly publishedAt?: string | Date;
  readonly images?: readonly SitemapImage[];
  readonly videos?: readonly SitemapVideo[];
  readonly noIndex?: boolean;
}

export interface PropertySitemapRecord extends SitemapSourceRecord {
  readonly name?: string;
  readonly locality?: string;
}

export interface LocalitySitemapRecord extends SitemapSourceRecord {
  readonly locality?: string;
  readonly city?: string;
}

export interface BlogSitemapRecord extends SitemapSourceRecord {
  readonly title?: string;
  readonly topic?: BlogTopic;
}

export interface SitemapEntry {
  readonly url: string;
  readonly type: SitemapPageType;
  readonly lastModified: Date;
  readonly changeFrequency: SitemapChangeFrequency;
  readonly priority: number;
  readonly images?: readonly SitemapImage[];
  readonly videos?: readonly SitemapVideo[];
}

export interface SitemapGeneratorInput {
  readonly baseUrl: string;
  readonly properties?: readonly PropertySitemapRecord[];
  readonly localities?: readonly LocalitySitemapRecord[];
  readonly blogs?: readonly BlogSitemapRecord[];
  readonly blogInputs?: readonly BlogGeneratorInput[];
  readonly blogTopics?: readonly BlogTopic[];
  readonly landingPages?: readonly LandingPageLocation[];
  readonly staticPages?: readonly SitemapSourceRecord[];
}

export interface SitemapGeneratorOptions {
  readonly propertyBasePath?: string;
  readonly localityBasePath?: string;
  readonly blogBasePath?: string;
  readonly landingBasePath?: string;
  readonly staticBasePath?: string;
  readonly now?: Date;
}

const DEFAULT_BLOG_TOPICS: readonly BlogTopic[] = [
  "bestPg",
  "costOfLiving",
  "luxuryPg",
  "singleSharing",
  "doubleSharing",
  "nearbyCompanies",
];

const DEFAULT_PRIORITIES: Record<SitemapPageType, number> = {
  property: 0.9,
  locality: 0.85,
  landing: 0.8,
  blog: 0.7,
  static: 0.6,
};

const DEFAULT_CHANGE_FREQUENCIES: Record<SitemapPageType, SitemapChangeFrequency> = {
  property: "daily",
  locality: "weekly",
  landing: "weekly",
  blog: "monthly",
  static: "monthly",
};

/**
 * Converts a date-like value into a valid Date and falls back to a supplied default.
 */
export function resolveLastModified(value: string | Date | undefined, fallback: Date): Date {
  if (!value) {
    return fallback;
  }

  const date = value instanceof Date ? value : new Date(value);

  return Number.isNaN(date.getTime()) ? fallback : date;
}

/**
 * Returns the freshest date available on a sitemap source record.
 */
export function getRecordLastModified(record: SitemapSourceRecord, fallback: Date): Date {
  return resolveLastModified(record.updatedAt ?? record.publishedAt ?? record.createdAt, fallback);
}

/**
 * Clamps priority to the valid sitemap range from 0.0 to 1.0.
 */
export function normalizeSitemapPriority(priority: number): number {
  return Math.max(0, Math.min(1, Number(priority.toFixed(2))));
}

/**
 * Builds a normalized sitemap entry with consistent defaults for priority and update frequency.
 */
export function createSitemapEntry(
  baseUrl: string,
  path: string,
  type: SitemapPageType,
  lastModified: Date,
  images: readonly SitemapImage[] = [],
  videos: readonly SitemapVideo[] = [],
): SitemapEntry {
  return {
    url: buildCanonicalUrl(baseUrl, path),
    type,
    lastModified,
    changeFrequency: DEFAULT_CHANGE_FREQUENCIES[type],
    priority: normalizeSitemapPriority(DEFAULT_PRIORITIES[type]),
    images,
    videos,
  };
}

/**
 * Removes noindex records and duplicate URLs while preserving the strongest entry.
 */
export function dedupeSitemapEntries(entries: readonly SitemapEntry[]): SitemapEntry[] {
  const byUrl = new Map<string, SitemapEntry>();

  for (const entry of entries) {
    const existing = byUrl.get(entry.url);

    if (!existing || entry.priority > existing.priority || entry.lastModified > existing.lastModified) {
      byUrl.set(entry.url, entry);
    }
  }

  return [...byUrl.values()].sort((first, second) => {
    if (second.priority !== first.priority) {
      return second.priority - first.priority;
    }

    return first.url.localeCompare(second.url);
  });
}

/**
 * Builds property sitemap entries from live property records.
 */
export function buildPropertySitemapEntries(
  records: readonly PropertySitemapRecord[],
  baseUrl: string,
  options: SitemapGeneratorOptions = {},
): SitemapEntry[] {
  const now = options.now ?? new Date();
  const basePath = options.propertyBasePath ?? "/properties";

  return records
    .filter((record) => !record.noIndex)
    .map((record) =>
      createSitemapEntry(baseUrl, `${basePath}/${record.slug}`, "property", getRecordLastModified(record, now), record.images ?? [], record.videos ?? []),
    );
}

/**
 * Builds locality sitemap entries from locality records.
 */
export function buildLocalitySitemapEntries(
  records: readonly LocalitySitemapRecord[],
  baseUrl: string,
  options: SitemapGeneratorOptions = {},
): SitemapEntry[] {
  const now = options.now ?? new Date();
  const basePath = options.localityBasePath ?? "/pg";

  return records
    .filter((record) => !record.noIndex)
    .map((record) =>
      createSitemapEntry(baseUrl, `${basePath}/${record.slug}`, "locality", getRecordLastModified(record, now), record.images ?? [], record.videos ?? []),
    );
}

/**
 * Builds blog sitemap entries from explicit blog records.
 */
export function buildBlogSitemapEntries(
  records: readonly BlogSitemapRecord[],
  baseUrl: string,
  options: SitemapGeneratorOptions = {},
): SitemapEntry[] {
  const now = options.now ?? new Date();
  const basePath = options.blogBasePath ?? "/blog";

  return records
    .filter((record) => !record.noIndex)
    .map((record) =>
      createSitemapEntry(baseUrl, `${basePath}/${record.slug}`, "blog", getRecordLastModified(record, now), record.images ?? [], record.videos ?? []),
    );
}

/**
 * Builds blog sitemap entries automatically from locality blog generator inputs.
 */
export function buildGeneratedBlogSitemapEntries(
  blogInputs: readonly BlogGeneratorInput[],
  baseUrl: string,
  options: SitemapGeneratorOptions & { readonly blogTopics?: readonly BlogTopic[] } = {},
): SitemapEntry[] {
  const now = options.now ?? new Date();
  const topics = options.blogTopics ?? DEFAULT_BLOG_TOPICS;
  const basePath = options.blogBasePath ?? "/blog";

  return blogInputs.flatMap((input) =>
    topics.map((topic) => {
      const title = getBlogTopicTitle(topic, input);

      return createSitemapEntry(baseUrl, `${basePath}/${createBlogSlug(title)}`, "blog", now);
    }),
  );
}

/**
 * Builds landing page sitemap entries from reusable landing page locations.
 */
export function buildLandingPageSitemapEntries(
  locations: readonly LandingPageLocation[],
  baseUrl: string,
  options: SitemapGeneratorOptions = {},
): SitemapEntry[] {
  const now = options.now ?? new Date();

  return locations.map((location) =>
    createSitemapEntry(
      baseUrl,
      buildLandingPagePath(location.slug ?? createLandingPageSlug(location.name), options.landingBasePath),
      "landing",
      now,
    ),
  );
}

/**
 * Builds static sitemap entries for important non-generated pages.
 */
export function buildStaticSitemapEntries(
  records: readonly SitemapSourceRecord[],
  baseUrl: string,
  options: SitemapGeneratorOptions = {},
): SitemapEntry[] {
  const now = options.now ?? new Date();
  const basePath = options.staticBasePath ?? "";

  return records
    .filter((record) => !record.noIndex)
    .map((record) =>
      createSitemapEntry(baseUrl, `${basePath}/${record.slug}`, "static", getRecordLastModified(record, now), record.images ?? [], record.videos ?? []),
    );
}

/**
 * Generates a complete deduped sitemap from properties, localities, blogs, landing pages, and static pages.
 */
export function generateSitemap(input: SitemapGeneratorInput, options: SitemapGeneratorOptions = {}): SitemapEntry[] {
  return dedupeSitemapEntries([
    ...buildPropertySitemapEntries(input.properties ?? [], input.baseUrl, options),
    ...buildLocalitySitemapEntries(input.localities ?? [], input.baseUrl, options),
    ...buildBlogSitemapEntries(input.blogs ?? [], input.baseUrl, options),
    ...buildGeneratedBlogSitemapEntries(input.blogInputs ?? [], input.baseUrl, {
      ...options,
      blogTopics: input.blogTopics,
    }),
    ...buildLandingPageSitemapEntries(input.landingPages ?? [], input.baseUrl, options),
    ...buildStaticSitemapEntries(input.staticPages ?? [], input.baseUrl, options),
  ]);
}

/**
 * Converts rich sitemap entries into the shape accepted by Next.js App Router sitemap.ts.
 */
export function toNextSitemap(entries: readonly SitemapEntry[]): MetadataRoute.Sitemap {
  return entries.map((entry) => ({
    url: entry.url,
    lastModified: entry.lastModified,
    changeFrequency: entry.changeFrequency,
    priority: entry.priority,
  }));
}

/**
 * Escapes XML text for sitemap serialization.
 */
export function escapeXml(value: string | number | boolean): string {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

/**
 * Serializes image metadata using the Google image sitemap extension.
 */
export function serializeSitemapImage(image: SitemapImage): string {
  return [
    "  <image:image>",
    `    <image:loc>${escapeXml(image.url)}</image:loc>`,
    image.caption ? `    <image:caption>${escapeXml(image.caption)}</image:caption>` : "",
    image.title ? `    <image:title>${escapeXml(image.title)}</image:title>` : "",
    image.geoLocation ? `    <image:geo_location>${escapeXml(image.geoLocation)}</image:geo_location>` : "",
    image.license ? `    <image:license>${escapeXml(image.license)}</image:license>` : "",
    "  </image:image>",
  ]
    .filter(Boolean)
    .join("\n");
}

/**
 * Serializes video metadata using the Google video sitemap extension.
 */
export function serializeSitemapVideo(video: SitemapVideo): string {
  return [
    "  <video:video>",
    `    <video:thumbnail_loc>${escapeXml(video.thumbnailUrl)}</video:thumbnail_loc>`,
    `    <video:title>${escapeXml(video.title)}</video:title>`,
    `    <video:description>${escapeXml(video.description)}</video:description>`,
    video.contentUrl ? `    <video:content_loc>${escapeXml(video.contentUrl)}</video:content_loc>` : "",
    video.playerUrl ? `    <video:player_loc>${escapeXml(video.playerUrl)}</video:player_loc>` : "",
    video.durationSeconds ? `    <video:duration>${video.durationSeconds}</video:duration>` : "",
    video.expirationDate ? `    <video:expiration_date>${new Date(video.expirationDate).toISOString()}</video:expiration_date>` : "",
    video.publicationDate ? `    <video:publication_date>${new Date(video.publicationDate).toISOString()}</video:publication_date>` : "",
    video.familyFriendly !== undefined ? `    <video:family_friendly>${video.familyFriendly ? "yes" : "no"}</video:family_friendly>` : "",
    video.live !== undefined ? `    <video:live>${video.live ? "yes" : "no"}</video:live>` : "",
    ...(video.tags ?? []).slice(0, 32).map((tag) => `    <video:tag>${escapeXml(tag)}</video:tag>`),
    "  </video:video>",
  ]
    .filter(Boolean)
    .join("\n");
}

/**
 * Serializes a full XML sitemap with image and video extensions.
 */
export function serializeSitemapXml(entries: readonly SitemapEntry[]): string {
  const urls = entries
    .map((entry) =>
      [
        "<url>",
        `  <loc>${escapeXml(entry.url)}</loc>`,
        `  <lastmod>${entry.lastModified.toISOString()}</lastmod>`,
        `  <changefreq>${entry.changeFrequency}</changefreq>`,
        `  <priority>${entry.priority.toFixed(2)}</priority>`,
        ...(entry.images ?? []).map(serializeSitemapImage),
        ...(entry.videos ?? []).map(serializeSitemapVideo),
        "</url>",
      ].join("\n"),
    )
    .join("\n");

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1" xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">',
    urls,
    "</urlset>",
  ].join("\n");
}
