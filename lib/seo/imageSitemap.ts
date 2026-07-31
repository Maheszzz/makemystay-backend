import { escapeXml, type SitemapEntry, type SitemapImage, type PropertySitemapRecord, type LocalitySitemapRecord, type BlogSitemapRecord } from "./sitemap";
import { generateImageAlt, generateImageTitle, generateImageCaption } from "./imageSeo";

export interface ImageSitemapOptions {
  readonly defaultGeoLocation?: string;
  readonly defaultLicense?: string;
  readonly maxImagesPerUrl?: number;
}

const DEFAULT_IMAGE_SITEMAP_OPTIONS: Required<ImageSitemapOptions> = {
  defaultGeoLocation: "Bangalore, Karnataka, India",
  defaultLicense: "https://makemystay.ai/terms",
  maxImagesPerUrl: 50, // Google limit is 1,000 images per page; we cap at 50 for performance
};

/**
 * Validates and normalizes an image URL for sitemaps.
 */
function normalizeSitemapImageUrl(url: string, baseUrl: string): string | undefined {
  if (!url || url.startsWith("data:") || url.startsWith("blob:")) {
    return undefined;
  }
  const trimmed = url.trim();
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
    return trimmed;
  }
  if (trimmed.startsWith("/")) {
    return `${baseUrl.replace(/\/+$/, "")}${trimmed}`;
  }
  return `${baseUrl.replace(/\/+$/, "")}/${trimmed}`;
}

/**
 * Extracts and enriches image records for a property sitemap entry.
 */
export function enrichPropertySitemapImages(
  property: PropertySitemapRecord,
  baseUrl: string,
  options: ImageSitemapOptions = {},
): readonly SitemapImage[] {
  const opts = { ...DEFAULT_IMAGE_SITEMAP_OPTIONS, ...options };
  const rawImages = property.images ?? [];
  const results: SitemapImage[] = [];

  for (let i = 0; i < rawImages.length && results.length < opts.maxImagesPerUrl; i++) {
    const rawImg = rawImages[i];
    const absoluteUrl = normalizeSitemapImageUrl(rawImg.url, baseUrl);
    if (!absoluteUrl) continue;

    const context = {
      propertyName: property.name ?? property.slug,
      locality: property.locality ?? "Bangalore",
      city: "Bangalore",
      index: i,
      totalImages: rawImages.length,
      isVerified: true,
    };

    results.push({
      url: absoluteUrl,
      title: rawImg.title ?? generateImageTitle(context),
      caption: rawImg.caption ?? generateImageCaption(context),
      geoLocation: rawImg.geoLocation ?? opts.defaultGeoLocation,
      license: rawImg.license ?? opts.defaultLicense,
    });
  }

  return results;
}

/**
 * Extracts and enriches image records for a locality sitemap entry.
 */
export function enrichLocalitySitemapImages(
  locality: LocalitySitemapRecord,
  baseUrl: string,
  options: ImageSitemapOptions = {},
): readonly SitemapImage[] {
  const opts = { ...DEFAULT_IMAGE_SITEMAP_OPTIONS, ...options };
  const rawImages = locality.images ?? [];
  const results: SitemapImage[] = [];

  for (let i = 0; i < rawImages.length && results.length < opts.maxImagesPerUrl; i++) {
    const rawImg = rawImages[i];
    const absoluteUrl = normalizeSitemapImageUrl(rawImg.url, baseUrl);
    if (!absoluteUrl) continue;

    const context = {
      locality: locality.locality ?? locality.slug,
      city: locality.city ?? "Bangalore",
      index: i,
    };

    results.push({
      url: absoluteUrl,
      title: rawImg.title ?? generateImageTitle(context),
      caption: rawImg.caption ?? generateImageCaption(context),
      geoLocation: rawImg.geoLocation ?? opts.defaultGeoLocation,
      license: rawImg.license ?? opts.defaultLicense,
    });
  }

  return results;
}

/**
 * Serializes a dedicated Google Image Sitemap XML file.
 */
export function generateImageSitemapXml(entries: readonly SitemapEntry[]): string {
  const entriesWithImages = entries.filter((entry) => entry.images && entry.images.length > 0);

  const urls = entriesWithImages
    .map((entry) => {
      const imageTags = (entry.images ?? [])
        .map((img) =>
          [
            "  <image:image>",
            `    <image:loc>${escapeXml(img.url)}</image:loc>`,
            img.caption ? `    <image:caption>${escapeXml(img.caption)}</image:caption>` : "",
            img.title ? `    <image:title>${escapeXml(img.title)}</image:title>` : "",
            img.geoLocation ? `    <image:geo_location>${escapeXml(img.geoLocation)}</image:geo_location>` : "",
            img.license ? `    <image:license>${escapeXml(img.license)}</image:license>` : "",
            "  </image:image>",
          ]
            .filter(Boolean)
            .join("\n"),
        )
        .join("\n");

      return [
        "<url>",
        `  <loc>${escapeXml(entry.url)}</loc>`,
        `  <lastmod>${entry.lastModified.toISOString()}</lastmod>`,
        imageTags,
        "</url>",
      ].join("\n");
    })
    .join("\n");

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
    urls,
    "</urlset>",
  ].join("\n");
}
