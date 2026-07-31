export type KeywordCategory =
  | "primary"
  | "secondary"
  | "longTail"
  | "nearby"
  | "commercialIntent";

export interface LocalityKeywordSet {
  readonly locality: string;
  readonly city: string;
  readonly primary: string;
  readonly secondary: readonly string[];
  readonly longTail: readonly string[];
  readonly nearby: readonly string[];
  readonly commercialIntent: readonly string[];
}

export type LocalityKeywordDatabase = Readonly<Record<string, LocalityKeywordSet>>;

export interface KeywordSearchOptions {
  readonly categories?: readonly KeywordCategory[];
  readonly includePrimary?: boolean;
}

const DEFAULT_KEYWORD_CATEGORIES: readonly KeywordCategory[] = [
  "secondary",
  "longTail",
  "nearby",
  "commercialIntent",
];

/**
 * Converts locality names into stable object keys for a large keyword database.
 */
export function createLocalityKey(locality: string, city?: string): string {
  const keyParts = [locality, city].filter(Boolean);

  return keyParts
    .join(" ")
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Normalizes keyword text for comparison while preserving display casing in the database.
 */
export function normalizeKeywordForComparison(keyword: string): string {
  return keyword.replace(/\s+/g, " ").trim().toLowerCase();
}

/**
 * Removes duplicate keywords from a list while preserving the first display value.
 */
export function uniqueKeywordList(keywords: readonly string[]): string[] {
  const seen = new Set<string>();
  const uniqueKeywords: string[] = [];

  for (const keyword of keywords) {
    const normalizedKeyword = normalizeKeywordForComparison(keyword);

    if (!normalizedKeyword || seen.has(normalizedKeyword)) {
      continue;
    }

    seen.add(normalizedKeyword);
    uniqueKeywords.push(keyword.trim());
  }

  return uniqueKeywords;
}

/**
 * Removes keywords already used by earlier categories so each locality has no cross-category duplicates.
 */
export function uniqueKeywordCategory(keywords: readonly string[], usedKeywords: Set<string>): string[] {
  const uniqueKeywords: string[] = [];

  for (const keyword of keywords) {
    const normalizedKeyword = normalizeKeywordForComparison(keyword);

    if (!normalizedKeyword || usedKeywords.has(normalizedKeyword)) {
      continue;
    }

    usedKeywords.add(normalizedKeyword);
    uniqueKeywords.push(keyword.trim());
  }

  return uniqueKeywords;
}

/**
 * Returns every keyword in a locality set according to the requested categories.
 */
export function getLocalityKeywords(
  keywordSet: LocalityKeywordSet,
  options: KeywordSearchOptions = {},
): string[] {
  const categories = options.categories ?? DEFAULT_KEYWORD_CATEGORIES;
  const keywords = options.includePrimary === false ? [] : [keywordSet.primary];

  for (const category of categories) {
    if (category === "primary") {
      keywords.push(keywordSet.primary);
      continue;
    }

    keywords.push(...keywordSet[category]);
  }

  return uniqueKeywordList(keywords);
}

/**
 * Creates a locality keyword set and guarantees there are no duplicates inside it.
 */
export function createLocalityKeywords(input: LocalityKeywordSet): LocalityKeywordSet {
  const usedKeywords = new Set<string>([normalizeKeywordForComparison(input.primary)]);
  const secondary = uniqueKeywordCategory(input.secondary, usedKeywords);
  const longTail = uniqueKeywordCategory(input.longTail, usedKeywords);
  const nearby = uniqueKeywordCategory(input.nearby, usedKeywords);
  const commercialIntent = uniqueKeywordCategory(input.commercialIntent, usedKeywords);

  return {
    locality: input.locality.trim(),
    city: input.city.trim(),
    primary: input.primary.trim(),
    secondary,
    longTail,
    nearby,
    commercialIntent,
  };
}

/**
 * Finds duplicate keyword phrases across a locality set after normalization.
 */
export function findDuplicateLocalityKeywords(keywordSet: LocalityKeywordSet): string[] {
  const seen = new Set<string>();
  const duplicates = new Set<string>();

  for (const keyword of getLocalityKeywords(keywordSet, { categories: DEFAULT_KEYWORD_CATEGORIES })) {
    const normalizedKeyword = normalizeKeywordForComparison(keyword);

    if (seen.has(normalizedKeyword)) {
      duplicates.add(keyword);
    }

    seen.add(normalizedKeyword);
  }

  return [...duplicates];
}

/**
 * Builds a typed database from locality keyword sets using generated locality keys.
 */
export function createKeywordDatabase(localities: readonly LocalityKeywordSet[]): LocalityKeywordDatabase {
  const database: Record<string, LocalityKeywordSet> = {};

  for (const localityKeywordSet of localities) {
    const normalizedKeywordSet = createLocalityKeywords(localityKeywordSet);
    const key = createLocalityKey(normalizedKeywordSet.locality, normalizedKeywordSet.city);

    if (database[key]) {
      throw new Error(`Duplicate SEO keyword locality key: ${key}`);
    }

    database[key] = normalizedKeywordSet;
  }

  return database;
}

export const localityKeywordEntries = [
  createLocalityKeywords({
    locality: "Whitefield",
    city: "Bengaluru",
    primary: "PG in Whitefield",
    secondary: [
      "Best PG Whitefield",
      "Luxury PG Whitefield",
      "Coliving Whitefield",
      "PG near ITPL",
      "PG near Whitefield Metro",
      "PG near SAP Whitefield",
      "PG near Accenture Whitefield",
      "PG near TCS Whitefield",
    ],
    longTail: [
      "Best PG in Whitefield for working professionals",
      "Luxury coliving PG in Whitefield with food",
      "Fully furnished PG in Whitefield near ITPL",
      "Single sharing PG in Whitefield near metro",
      "Premium PG in Whitefield for men and women",
    ],
    nearby: [
      "PG near ITPL Whitefield",
      "PG near SAP Labs Whitefield",
      "PG near Accenture Whitefield",
      "PG near TCS Whitefield",
      "PG near EPIP Zone Whitefield",
      "PG near Kadugodi Metro",
      "PG near Hope Farm Junction",
    ],
    commercialIntent: [
      "Book PG in Whitefield",
      "PG rent in Whitefield",
      "Affordable PG in Whitefield",
      "Premium PG rooms in Whitefield",
      "Verified PG in Whitefield",
      "Move in ready PG Whitefield",
    ],
  }),
  createLocalityKeywords({
    locality: "Electronic City",
    city: "Bengaluru",
    primary: "PG in Electronic City",
    secondary: [
      "Best PG Electronic City",
      "Luxury PG Electronic City",
      "Coliving Electronic City",
      "PG near Infosys Electronic City",
      "PG near Wipro Electronic City",
      "PG near Tech Mahindra Electronic City",
    ],
    longTail: [
      "Best PG in Electronic City Phase 1 for professionals",
      "Fully furnished PG in Electronic City with food",
      "Affordable coliving PG near Infosys Electronic City",
      "Single sharing PG in Electronic City for working women",
      "Premium PG in Electronic City near tech parks",
    ],
    nearby: [
      "PG near Infosys Electronic City",
      "PG near Wipro Gate Electronic City",
      "PG near Electronic City Phase 1",
      "PG near Electronic City Phase 2",
      "PG near Neeladri Road",
      "PG near Velankani Tech Park",
    ],
    commercialIntent: [
      "Book PG in Electronic City",
      "PG rent in Electronic City",
      "Affordable PG in Electronic City",
      "Verified PG in Electronic City",
      "Premium PG rooms in Electronic City",
      "Immediate occupancy PG Electronic City",
    ],
  }),
  createLocalityKeywords({
    locality: "Marathahalli",
    city: "Bengaluru",
    primary: "PG in Marathahalli",
    secondary: [
      "Best PG Marathahalli",
      "Luxury PG Marathahalli",
      "Coliving Marathahalli",
      "PG near Marathahalli Bridge",
      "PG near Outer Ring Road Marathahalli",
      "PG near Embassy Tech Village",
    ],
    longTail: [
      "Best PG in Marathahalli for IT professionals",
      "Fully furnished PG in Marathahalli near Outer Ring Road",
      "Affordable coliving PG near Marathahalli Bridge",
      "Luxury PG in Marathahalli with meals and WiFi",
      "Single sharing PG in Marathahalli for working professionals",
    ],
    nearby: [
      "PG near Marathahalli Bridge",
      "PG near Kalamandir Marathahalli",
      "PG near Outer Ring Road Marathahalli",
      "PG near Embassy Tech Village",
      "PG near Cessna Business Park",
      "PG near Kadubeesanahalli",
    ],
    commercialIntent: [
      "Book PG in Marathahalli",
      "PG rent in Marathahalli",
      "Affordable PG in Marathahalli",
      "Verified PG in Marathahalli",
      "Premium PG rooms in Marathahalli",
      "Move in ready PG Marathahalli",
    ],
  }),
  createLocalityKeywords({
    locality: "Koramangala",
    city: "Bengaluru",
    primary: "PG in Koramangala",
    secondary: [
      "Best PG Koramangala",
      "Luxury PG Koramangala",
      "Coliving Koramangala",
      "PG near Forum Mall Koramangala",
      "PG near Jyoti Nivas College",
      "PG near Koramangala Sony Signal",
    ],
    longTail: [
      "Best PG in Koramangala for students and professionals",
      "Luxury coliving PG in Koramangala with food",
      "Fully furnished PG in Koramangala near Forum Mall",
      "Single sharing PG in Koramangala for women",
      "Premium PG in Koramangala near startup offices",
    ],
    nearby: [
      "PG near Forum Mall Koramangala",
      "PG near Jyoti Nivas College",
      "PG near Sony Signal Koramangala",
      "PG near Koramangala 5th Block",
      "PG near Koramangala 6th Block",
      "PG near Christ University",
    ],
    commercialIntent: [
      "Book PG in Koramangala",
      "PG rent in Koramangala",
      "Affordable PG in Koramangala",
      "Verified PG in Koramangala",
      "Premium PG rooms in Koramangala",
      "Immediate occupancy PG Koramangala",
    ],
  }),
  createLocalityKeywords({
    locality: "HSR Layout",
    city: "Bengaluru",
    primary: "PG in HSR Layout",
    secondary: [
      "Best PG HSR Layout",
      "Luxury PG HSR Layout",
      "Coliving HSR Layout",
      "PG near HSR BDA Complex",
      "PG near Agara",
      "PG near Silk Board",
    ],
    longTail: [
      "Best PG in HSR Layout for working professionals",
      "Luxury coliving PG in HSR Layout with food",
      "Fully furnished PG in HSR Layout near startups",
      "Single sharing PG in HSR Layout for men and women",
      "Affordable PG in HSR Layout near Silk Board",
    ],
    nearby: [
      "PG near HSR BDA Complex",
      "PG near Agara Lake",
      "PG near Silk Board",
      "PG near HSR Sector 1",
      "PG near HSR Sector 2",
      "PG near Haralur Road",
    ],
    commercialIntent: [
      "Book PG in HSR Layout",
      "PG rent in HSR Layout",
      "Affordable PG in HSR Layout",
      "Verified PG in HSR Layout",
      "Premium PG rooms in HSR Layout",
      "Move in ready PG HSR Layout",
    ],
  }),
] as const satisfies readonly LocalityKeywordSet[];

export const localityKeywordDatabase = createKeywordDatabase(localityKeywordEntries);

/**
 * Looks up a locality keyword set by locality and optional city.
 */
export function getLocalityKeywordSet(locality: string, city?: string): LocalityKeywordSet | undefined {
  return localityKeywordDatabase[createLocalityKey(locality, city)];
}

/**
 * Returns all keyword sets as an array for sitemap, static params, or batch SEO generation.
 */
export function getAllLocalityKeywordSets(): LocalityKeywordSet[] {
  return Object.values(localityKeywordDatabase);
}

/**
 * Returns all keywords for a locality key, with optional category filtering.
 */
export function getKeywordsByLocalityKey(localityKey: string, options: KeywordSearchOptions = {}): string[] {
  const keywordSet = localityKeywordDatabase[localityKey];

  return keywordSet ? getLocalityKeywords(keywordSet, options) : [];
}
