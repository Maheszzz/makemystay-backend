import type { Metadata } from "next"; 

import { buildBreadcrumbs, type BreadcrumbItem } from "./breadcrumbs";
import { generateSeoFaqs, type FaqItem } from "./faq";
import { createInternalLink, type InternalLink, selectInternalLinks } from "./internalLinks";
import {
  type LocalityPointOfInterest,
  countWords,
  formatLocalityRent,
  joinNames,
  localityContentToText,
  normalizeParagraphKey,
} from "./localityContent";
import { buildCanonicalUrl, buildMetadata, type SeoDefaults } from "./metadata";
import { generateSchema, type JsonLdObject } from "./schema";

export type BlogTopic =
  | "bestPg"
  | "costOfLiving"
  | "luxuryPg"
  | "singleSharing"
  | "doubleSharing"
  | "nearbyCompanies";

export interface BlogGeneratorInput {
  readonly locality: string;
  readonly city: string;
  readonly propertyType?: string;
  readonly rent?: string | number;
  readonly rentRange?: string;
  readonly amenities?: readonly string[];
  readonly nearbyCompanies?: readonly LocalityPointOfInterest[];
  readonly nearbyAreas?: readonly LocalityPointOfInterest[];
  readonly internalLinks?: readonly InternalLink[];
  readonly image?: string;
  readonly brandName?: string;
}

export interface BlogGeneratorOptions {
  readonly basePath?: string;
  readonly topics?: readonly BlogTopic[];
  readonly internalLinkLimit?: number;
  readonly faqCount?: number;
}

export interface BlogArticleSection {
  readonly heading: string;
  readonly paragraphs: readonly string[];
}

export interface BlogArticle {
  readonly topic: BlogTopic;
  readonly slug: string;
  readonly path: string;
  readonly canonicalUrl: string;
  readonly title: string;
  readonly description: string;
  readonly metadata: Metadata;
  readonly schema: JsonLdObject;
  readonly breadcrumbs: readonly BreadcrumbItem[];
  readonly internalLinks: readonly InternalLink[];
  readonly faqs: readonly FaqItem[];
  readonly sections: readonly BlogArticleSection[];
  readonly wordCount: number;
}

export interface BlogGeneratorResult {
  readonly locality: string;
  readonly city: string;
  readonly articles: readonly BlogArticle[];
}

const DEFAULT_BLOG_TOPICS: readonly BlogTopic[] = [
  "bestPg",
  "costOfLiving",
  "luxuryPg",
  "singleSharing",
  "doubleSharing",
  "nearbyCompanies",
];

/**
 * Converts text into a stable blog slug segment.
 */
export function createBlogSlug(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Builds a canonical blog path for a locality article.
 */
export function buildBlogPath(slug: string, basePath = "/blog"): string {
  return `/${[basePath.replace(/^\/+|\/+$/g, ""), slug].filter(Boolean).join("/")}`;
}

/**
 * Returns the SEO title for a generated blog topic.
 */
export function getBlogTopicTitle(topic: BlogTopic, input: BlogGeneratorInput): string {
  const propertyType = input.propertyType ?? "PG";

  switch (topic) {
    case "bestPg":
      return `Best ${propertyType} in ${input.locality}`;
    case "costOfLiving":
      return `Cost of Living in ${input.locality}`;
    case "luxuryPg":
      return `Luxury ${propertyType} in ${input.locality}`;
    case "singleSharing":
      return `Single Sharing ${propertyType} in ${input.locality}`;
    case "doubleSharing":
      return `Double Sharing ${propertyType} in ${input.locality}`;
    case "nearbyCompanies":
      return `Companies near ${input.locality} for ${propertyType} Residents`;
  }
}

/**
 * Builds unique SEO keywords for a blog topic.
 */
export function buildBlogKeywords(topic: BlogTopic, input: BlogGeneratorInput): string[] {
  const title = getBlogTopicTitle(topic, input);
  const propertyType = input.propertyType ?? "PG";

  return [
    title,
    `${propertyType} in ${input.locality}`,
    `${propertyType} in ${input.locality} ${input.city}`,
    `rent in ${input.locality}`,
    topic === "luxuryPg" ? `premium ${propertyType} in ${input.locality}` : "",
    topic === "singleSharing" ? `single room ${propertyType} in ${input.locality}` : "",
    topic === "doubleSharing" ? `double sharing room ${propertyType} in ${input.locality}` : "",
    topic === "nearbyCompanies" ? `companies near ${input.locality}` : "",
  ].filter(Boolean);
}

/**
 * Builds SEO description copy for a generated blog article.
 */
export function buildBlogDescription(topic: BlogTopic, input: BlogGeneratorInput): string {
  const title = getBlogTopicTitle(topic, input);
  const rent = formatLocalityRent(input.rent, input.rentRange);
  const amenities = joinNames(input.amenities ?? [], "WiFi, food, laundry and housekeeping");

  return `${title}: compare rent, amenities, commute, room types and nearby companies in ${input.locality}, ${input.city}. Rent reference: ${rent}. Amenities to compare include ${amenities}.`;
}

/**
 * Removes duplicate blog paragraphs while preserving the article structure.
 */
export function dedupeBlogSections(sections: readonly BlogArticleSection[]): BlogArticleSection[] {
  const seen = new Set<string>();

  return sections.map((section) => ({
    ...section,
    paragraphs: section.paragraphs.filter((paragraph) => {
      const key = normalizeParagraphKey(paragraph);

      if (!key || seen.has(key)) {
        return false;
      }

      seen.add(key);
      return true;
    }),
  }));
}

/**
 * Serializes blog article sections for word counts and search indexing.
 */
export function blogSectionsToText(sections: readonly BlogArticleSection[], faqs: readonly FaqItem[] = []): string {
  return localityContentToText([
    {
      id: "aboutArea",
      heading: "Blog",
      paragraphs: sections.flatMap((section) => [section.heading, ...section.paragraphs]),
      faqs,
    },
  ]);
}

/**
 * Builds article sections for one SEO blog topic from locality data.
 */
export function buildBlogSections(topic: BlogTopic, input: BlogGeneratorInput): BlogArticleSection[] {
  const propertyType = input.propertyType ?? "PG";
  const brandName = input.brandName ?? "MakeMyStay";
  const rent = formatLocalityRent(input.rent, input.rentRange);
  const amenities = joinNames(input.amenities ?? [], "WiFi, food, laundry, housekeeping and security");
  const companies = joinNames((input.nearbyCompanies ?? []).map((company) => company.name), "nearby offices, tech parks and business hubs");
  const nearbyAreas = joinNames((input.nearbyAreas ?? []).map((area) => area.name), "well-connected nearby areas");

  const commonIntro = `${input.locality}, ${input.city} is a practical rental market for people comparing ${propertyType} options by commute, rent, room type, amenities and day-to-day convenience. A useful blog page should answer the search intent directly and then guide readers toward related pages through internal links.`;

  const topicSections: Record<BlogTopic, readonly BlogArticleSection[]> = {
    bestPg: [
      {
        heading: `How to choose the best ${propertyType} in ${input.locality}`,
        paragraphs: [
          commonIntro,
          `The best ${propertyType} in ${input.locality} is not simply the cheapest or the newest building. It is the stay that fits your commute, budget, food preference, sharing choice and comfort expectations. Start by comparing verified photos, rent inclusions, room size, security, cleaning frequency and resident reviews.`,
          `For most users, the strongest options include ${amenities}. These amenities matter because they affect daily routine more than decorative features. Reliable WiFi, clean bathrooms, safe entry, drinking water and transparent house rules should carry more weight than short-term discounts.`,
        ],
      },
      {
        heading: `Best areas and commute points in ${input.locality}`,
        paragraphs: [
          `Readers should compare ${input.locality} with ${nearbyAreas} when deciding where to stay. A nearby lane can change travel time, noise level, food access and cab availability, so area-level comparison improves both SEO depth and user confidence.`,
          `People working near ${companies} should prioritize realistic commute time over map distance. Peak-hour traffic, last-mile transport and road quality can change the value of a stay even when two properties look close on a map.`,
        ],
      },
    ],
    costOfLiving: [
      {
        heading: `Cost of living in ${input.locality}`,
        paragraphs: [
          commonIntro,
          `The cost of living in ${input.locality} depends on rent, food, transport, laundry, electricity, internet, personal expenses and how often you commute. For ${propertyType} accommodation, a useful rent reference is ${rent}, but total monthly cost should include every recurring charge.`,
          `Managed stays can simplify budgeting because services such as ${amenities} may be bundled into rent. Users should still confirm what is included, what is chargeable and whether electricity, food upgrades or laundry limits affect the final monthly amount.`,
        ],
      },
      {
        heading: `Budget planning for ${input.locality}`,
        paragraphs: [
          `A realistic budget should account for deposit, setup costs, commute, meals outside the property, subscriptions and weekend travel. Students may prioritize affordability and food, while working professionals may pay more for shorter commute and quieter rooms.`,
          `Internal links from this article should guide readers to best ${propertyType}, single sharing, double sharing and luxury options in ${input.locality}. This helps users move from research intent to comparison intent without leaving the site journey.`,
        ],
      },
    ],
    luxuryPg: [
      {
        heading: `What makes a luxury ${propertyType} in ${input.locality}`,
        paragraphs: [
          commonIntro,
          `Luxury ${propertyType} options in ${input.locality} usually stand out through better interiors, larger rooms, improved common spaces, stronger maintenance and more predictable service quality. Users should check whether premium rent is justified by actual comfort, not only branding.`,
          `Premium amenities can include ${amenities}, but quality and consistency are more important than a long amenity list. Good luxury stays should reduce friction in everyday life through cleanliness, responsive support, security and dependable facilities.`,
        ],
      },
      {
        heading: `Who should choose premium stays in ${input.locality}`,
        paragraphs: [
          `Luxury stays are useful for residents who value privacy, better room design, lower maintenance hassle and proximity to ${companies}. They may also suit people relocating to ${input.city} who want a ready-to-move option without handling furniture, internet and services separately.`,
          `A premium ${propertyType} page should internally link to budget, single sharing and double sharing articles so readers can compare whether the upgrade is worth the additional monthly cost.`,
        ],
      },
    ],
    singleSharing: [
      {
        heading: `Single sharing ${propertyType} in ${input.locality}`,
        paragraphs: [
          commonIntro,
          `Single sharing ${propertyType} options in ${input.locality} are ideal for residents who want more privacy, quieter routines and better control over their room environment. They usually cost more than shared rooms, but the value can be strong for people with demanding work or study schedules.`,
          `Before booking a single sharing room, users should check room size, ventilation, attached bathroom, work desk, storage, WiFi quality and whether services such as ${amenities} are included. These details decide whether the higher rent feels worthwhile over a longer stay.`,
        ],
      },
      {
        heading: `Single sharing rent and availability`,
        paragraphs: [
          `A practical rent reference for ${input.locality} is ${rent}, though single sharing rooms may sit at the higher end of the range. Availability can change quickly near ${companies}, especially when office attendance or college sessions increase.`,
          `This article should link users to double sharing, luxury and best ${propertyType} guides so they can compare privacy, cost and amenities before making a decision.`,
        ],
      },
    ],
    doubleSharing: [
      {
        heading: `Double sharing ${propertyType} in ${input.locality}`,
        paragraphs: [
          commonIntro,
          `Double sharing ${propertyType} options in ${input.locality} are popular because they balance affordability and comfort. They usually cost less than single sharing rooms while still offering better space and routine control than larger shared formats.`,
          `Users should compare bed size, cupboard space, bathroom sharing, cleaning frequency, food plan, roommate rules and access to ${amenities}. A good double sharing room should feel manageable for daily work or study, not just cheaper on paper.`,
        ],
      },
      {
        heading: `Who should choose double sharing`,
        paragraphs: [
          `Double sharing works well for students, new joiners, interns and working professionals who want to control rent while staying close to ${companies}. It can also suit friends moving together or residents who are comfortable sharing space with one roommate.`,
          `Internal links should point readers to single sharing, cost of living and best ${propertyType} pages because these are the natural next questions after someone compares double sharing options.`,
        ],
      },
    ],
    nearbyCompanies: [
      {
        heading: `Nearby companies around ${input.locality}`,
        paragraphs: [
          commonIntro,
          `Nearby companies and office hubs strongly influence rental demand in ${input.locality}. Important work locations include ${companies}. People usually prefer ${propertyType} options that reduce commute time and keep late-evening travel manageable.`,
          `The best stay for office access depends on shift timing, cab availability, bus or metro access, road conditions and how often the resident needs to travel. A property close to the office is useful only when the route is reliable during actual commute hours.`,
        ],
      },
      {
        heading: `How companies affect rent and room demand`,
        paragraphs: [
          `Rent near major companies can be higher because demand is consistent from employees, interns and relocating professionals. A reference such as ${rent} helps users plan, but final pricing depends on sharing type, property quality and included services.`,
          `This article should internally link to best ${propertyType}, single sharing, double sharing and luxury guides so readers can move from company-based search intent to room-type comparison.`,
        ],
      },
    ],
  };

  return dedupeBlogSections(topicSections[topic]);
}

/**
 * Builds internal links that connect every generated locality blog article.
 */
export function buildBlogInternalLinks(
  currentPath: string,
  input: BlogGeneratorInput,
  topics: readonly BlogTopic[],
  basePath = "/blog",
  limit = 12,
): InternalLink[] {
  const articleLinks = topics.map((topic) => {
    const title = getBlogTopicTitle(topic, input);
    const slug = createBlogSlug(title);

    return createInternalLink(title, buildBlogPath(slug, basePath), {
      priority: 80,
      tags: ["blog", "locality", topic],
    });
  });

  const localityLinks = [
    createInternalLink(`${input.propertyType ?? "PG"} in ${input.locality}`, `/pg/${createBlogSlug(input.locality)}`, {
      priority: 90,
      tags: ["locality", "money"],
    }),
    ...(input.nearbyCompanies ?? []).map((company) =>
      createInternalLink(`${input.propertyType ?? "PG"} near ${company.name}`, `/pg-near/${createBlogSlug(company.name)}`, {
        priority: 70,
        tags: ["landing", "company"],
      }),
    ),
  ];

  return selectInternalLinks([...(input.internalLinks ?? []), ...articleLinks, ...localityLinks], {
    currentPath,
    tags: ["blog", "locality", "landing", "company", "money"],
    limit,
  });
}

/**
 * Generates one SEO-optimized blog article for a locality and topic.
 */
export function generateBlogArticle(
  topic: BlogTopic,
  input: BlogGeneratorInput,
  defaults: SeoDefaults,
  options: BlogGeneratorOptions = {},
): BlogArticle {
  const topics = options.topics ?? DEFAULT_BLOG_TOPICS;
  const title = getBlogTopicTitle(topic, input);
  const slug = createBlogSlug(title);
  const path = buildBlogPath(slug, options.basePath);
  const canonicalUrl = buildCanonicalUrl(defaults.baseUrl, path);
  const description = buildBlogDescription(topic, input);
  const metadata = buildMetadata(
    {
      title,
      description,
      path,
      image: input.image,
      keywords: buildBlogKeywords(topic, input),
      locations: [input.locality, input.city],
      type: "article",
    },
    defaults,
  );
  const faqs = generateSeoFaqs(
    {
      locality: input.locality,
      city: input.city,
      propertyType: input.propertyType ?? "PG",
      amenities: input.amenities,
      rent: input.rentRange ?? input.rent,
      brandName: input.brandName,
    },
    { count: options.faqCount ?? 8 },
  );
  const breadcrumbs = buildBreadcrumbs(path, {
    baseUrl: defaults.baseUrl,
    labels: {
      [slug]: title,
    },
  });
  const sections = buildBlogSections(topic, input);
  const internalLinks = buildBlogInternalLinks(path, input, topics, options.basePath, options.internalLinkLimit ?? 12);
  const schema = generateSchema({
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
      name: title,
      url: canonicalUrl,
      description,
      image: input.image ?? defaults.defaultImage,
    },
    breadcrumb: breadcrumbs,
    faq: faqs,
  });
  const wordCount = countWords(blogSectionsToText(sections, faqs));

  return {
    topic,
    slug,
    path,
    canonicalUrl,
    title,
    description,
    metadata,
    schema,
    breadcrumbs,
    internalLinks,
    faqs,
    sections,
    wordCount,
  };
}

/**
 * Generates all requested locality blog articles from one reusable input.
 */
export function generateLocalityBlog(
  input: BlogGeneratorInput,
  defaults: SeoDefaults,
  options: BlogGeneratorOptions = {},
): BlogGeneratorResult {
  const topics = options.topics ?? DEFAULT_BLOG_TOPICS;

  return {
    locality: input.locality,
    city: input.city,
    articles: topics.map((topic) => generateBlogArticle(topic, input, defaults, { ...options, topics })),
  };
}

/**
 * Returns generated blog content as JSON for static generation or API workflows.
 */
export function generateLocalityBlogJson(
  input: BlogGeneratorInput,
  defaults: SeoDefaults,
  options: BlogGeneratorOptions = {},
): string {
  return JSON.stringify(generateLocalityBlog(input, defaults, options), null, 2);
}
