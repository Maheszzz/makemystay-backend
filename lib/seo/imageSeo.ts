import { buildImageObjectSchema, type ImageObjectSchemaInput } from "./schema/imageObject";
import type { JsonLdObject } from "./schema/types";

export type ImageLayoutPreset = "hero" | "card" | "grid" | "full" | "thumbnail";

export interface ImageSeoContext {
  readonly propertyName?: string;
  readonly locality?: string;
  readonly city?: string;
  readonly category?: string;
  readonly roomType?: string;
  readonly index?: number;
  readonly totalImages?: number;
  readonly isVerified?: boolean;
  readonly customAlt?: string;
  readonly customTitle?: string;
  readonly customCaption?: string;
  readonly author?: string;
  readonly license?: string;
}

export interface ImageSeoInput {
  readonly url: string;
  readonly context?: ImageSeoContext;
  readonly layout?: ImageLayoutPreset;
  readonly priority?: boolean;
  readonly width?: number;
  readonly height?: number;
  readonly customSizes?: string;
  readonly customWidths?: readonly number[];
}

export interface ImageSeoResult {
  readonly url: string;
  readonly alt: string;
  readonly title: string;
  readonly caption: string;
  readonly srcSet: string;
  readonly sizes: string;
  readonly loading: "lazy" | "eager";
  readonly decoding: "async";
  readonly fetchPriority: "auto" | "high" | "low";
  readonly width?: number;
  readonly height?: number;
  readonly structuredData: JsonLdObject;
}

export interface ImageSeoAuditResult {
  readonly score: number;
  readonly grade: "A+" | "A" | "B" | "C" | "F";
  readonly passed: readonly string[];
  readonly warnings: readonly string[];
  readonly issues: readonly string[];
}

const DEFAULT_RESPONSIVE_WIDTHS: Record<ImageLayoutPreset, readonly number[]> = {
  hero: [640, 800, 1024, 1280, 1600, 1920],
  full: [640, 800, 1024, 1280, 1600],
  card: [320, 400, 640, 800],
  grid: [320, 480, 640, 800, 1024],
  thumbnail: [150, 300, 400],
};

const DEFAULT_RESPONSIVE_SIZES: Record<ImageLayoutPreset, string> = {
  hero: "100vw",
  full: "(max-width: 1024px) 100vw, 1280px",
  card: "(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw",
  grid: "(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw",
  thumbnail: "(max-width: 640px) 50vw, 200px",
};

/**
 * Automatically generates SEO-optimized, accessible alt text from entity context.
 */
export function generateImageAlt(context: ImageSeoContext = {}): string {
  if (context.customAlt?.trim()) {
    return context.customAlt.trim();
  }

  const parts: string[] = [];
  if (context.roomType) {
    parts.push(context.roomType.trim());
  } else if (context.category) {
    parts.push(`${context.category.trim()} accommodation`);
  } else {
    parts.push("Property view");
  }

  if (context.propertyName) {
    parts.push(`at ${context.propertyName.trim()}`);
  }

  if (context.locality) {
    parts.push(`in ${context.locality.trim()}`);
  }

  if (context.city && !context.locality?.toLowerCase().includes(context.city.toLowerCase())) {
    parts.push(context.city.trim());
  }

  if (context.isVerified) {
    parts.push("- Verified Stay");
  }

  const baseAlt = parts.join(" ").replace(/\s+/g, " ").trim();
  if (context.index !== undefined && context.index > 0) {
    return `${baseAlt} - photo ${context.index + 1}`;
  }
  return baseAlt || "Verified PG accommodation in Bangalore";
}

/**
 * Automatically generates a clean tooltip title attribute for hover and accessibility.
 */
export function generateImageTitle(context: ImageSeoContext = {}): string {
  if (context.customTitle?.trim()) {
    return context.customTitle.trim();
  }

  const name = context.propertyName ? context.propertyName.trim() : "Verified PG Stay";
  const location = [context.locality, context.city].filter(Boolean).join(", ");
  const suffix = location ? ` (${location})` : "";
  const photoIndex = context.index !== undefined && context.index > 0 ? ` [Photo ${context.index + 1}]` : "";

  return `${name}${suffix}${photoIndex}`.trim();
}

/**
 * Automatically generates an informative figure caption text for display.
 */
export function generateImageCaption(context: ImageSeoContext = {}): string {
  if (context.customCaption?.trim()) {
    return context.customCaption.trim();
  }

  const name = context.propertyName ? context.propertyName.trim() : "MakeMyStay Property";
  const room = context.roomType ? `${context.roomType.trim()} at ` : "";
  const location = [context.locality, context.city || "Bangalore"].filter(Boolean).join(", ");
  const verifiedBadge = context.isVerified ? " (Verified Property)" : "";
  const photoIndex =
    context.index !== undefined && context.totalImages && context.totalImages > 1
      ? ` — Photo ${context.index + 1} of ${context.totalImages}`
      : "";

  return `${room}${name}, ${location}${verifiedBadge}${photoIndex}`.trim();
}

/**
 * Calculates a responsive srcset string with multiple widths.
 * Automatically applies Unsplash or CDN sizing params when applicable.
 */
export function generateResponsiveSrcSet(
  url: string,
  layout: ImageLayoutPreset = "card",
  customWidths?: readonly number[],
): string {
  if (!url || url.startsWith("data:") || url.startsWith("blob:")) {
    return "";
  }

  const widths = customWidths && customWidths.length > 0 ? customWidths : DEFAULT_RESPONSIVE_WIDTHS[layout];
  const isUnsplash = url.includes("images.unsplash.com");

  return widths
    .map((w) => {
      let resizedUrl = url;
      if (isUnsplash) {
        const baseUrl = url.split("?")[0];
        resizedUrl = `${baseUrl}?auto=format,compress&fit=crop&q=80&w=${w}`;
      }
      return `${resizedUrl} ${w}w`;
    })
    .join(", ");
}

/**
 * Core Image SEO Engine: Generates complete SEO attributes, structured data, and responsive properties.
 */
export function generateImageSeo(input: ImageSeoInput): ImageSeoResult {
  const context = input.context ?? {};
  const layout = input.layout ?? "card";

  const alt = generateImageAlt(context);
  const title = generateImageTitle(context);
  const caption = generateImageCaption(context);

  const srcSet = generateResponsiveSrcSet(input.url, layout, input.customWidths);
  const sizes = input.customSizes ?? DEFAULT_RESPONSIVE_SIZES[layout];

  const priority = input.priority === true;
  const loading = priority ? "eager" : "lazy";
  const fetchPriority = priority ? "high" : "auto";

  const schemaInput: ImageObjectSchemaInput = {
    url: input.url,
    name: title,
    caption: caption,
    description: alt,
    width: input.width,
    height: input.height,
    author: context.author,
    license: context.license,
    representativeOfPage: priority || (context.index !== undefined && context.index === 0),
  };

  const structuredData = buildImageObjectSchema(schemaInput);

  return {
    url: input.url,
    alt,
    title,
    caption,
    srcSet,
    sizes,
    loading,
    decoding: "async",
    fetchPriority,
    width: input.width,
    height: input.height,
    structuredData,
  };
}

/**
 * Diagnoses and scores an image's SEO quality on a 0–100 scale.
 */
export function analyzeImageSeoScore(result: ImageSeoResult): ImageSeoAuditResult {
  const passed: string[] = [];
  const warnings: string[] = [];
  const issues: string[] = [];
  let score = 100;

  // 1. Alt Text Analysis
  if (!result.alt || !result.alt.trim()) {
    issues.push("Missing alt text attribute.");
    score -= 30;
  } else if (result.alt.length < 15) {
    warnings.push("Alt text is too short (< 15 characters); add descriptive location/property context.");
    score -= 10;
  } else if (result.alt.length > 130) {
    warnings.push("Alt text is very long (> 130 characters); consider making it more concise.");
    score -= 5;
  } else {
    passed.push("Alt text is descriptive and well-formatted.");
  }

  // 2. Title Attribute Analysis
  if (result.title && result.title.length > 0) {
    passed.push("Title tooltip attribute is present.");
  } else {
    warnings.push("Title tooltip attribute is missing.");
    score -= 5;
  }

  // 3. Caption Analysis
  if (result.caption && result.caption.length > 0) {
    passed.push("Figure caption text is generated.");
  } else {
    warnings.push("Figure caption text is missing.");
    score -= 5;
  }

  // 4. Responsive Image Analysis
  if (result.srcSet && result.srcSet.includes("w")) {
    passed.push("Responsive srcSet attribute configured across multiple viewport widths.");
  } else {
    warnings.push("Responsive srcSet is missing or does not define widths.");
    score -= 10;
  }

  // 5. Lazy Loading & Performance
  if (result.loading === "lazy" || result.fetchPriority === "high") {
    passed.push(`Optimal loading strategy configured (${result.loading}, fetchPriority=${result.fetchPriority}).`);
  } else {
    warnings.push("Image loading strategy is not explicitly optimized.");
    score -= 10;
  }

  // 6. Dimensions Analysis
  if (result.width && result.height) {
    passed.push("Explicit width and height provided to prevent Cumulative Layout Shift (CLS).");
  } else {
    warnings.push("Missing explicit width and height dimensions; could cause layout shift.");
    score -= 15;
  }

  // 7. Structured Data
  if (result.structuredData && result.structuredData["@type"] === "ImageObject") {
    passed.push("Valid Schema.org ImageObject structured data generated.");
  } else {
    issues.push("ImageObject structured data is missing.");
    score -= 20;
  }

  const boundedScore = Math.max(0, Math.min(100, score));
  let grade: "A+" | "A" | "B" | "C" | "F" = "F";
  if (boundedScore >= 95) grade = "A+";
  else if (boundedScore >= 85) grade = "A";
  else if (boundedScore >= 75) grade = "B";
  else if (boundedScore >= 60) grade = "C";

  return {
    score: boundedScore,
    grade,
    passed,
    warnings,
    issues,
  };
}
