export interface FaqItem {
  readonly question: string;
  readonly answer: string;
}

export interface SeoFaqGeneratorInput {
  readonly locality: string;
  readonly propertyType: string;
  readonly amenities?: readonly string[];
  readonly rent?: string | number;
  readonly city?: string;
  readonly brandName?: string;
}

export interface SeoFaqGeneratorOptions {
  readonly count?: number;
}

const DEFAULT_FAQ_COUNT = 15;

/**
 * Normalizes FAQ text to prevent duplicate questions caused by whitespace differences.
 */
export function normalizeFaqText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

/**
 * Creates a validated FAQ item or returns null when required content is missing.
 */
export function createFaqItem(question: string, answer: string): FaqItem | null {
  const normalizedQuestion = normalizeFaqText(question);
  const normalizedAnswer = normalizeFaqText(answer);

  if (!normalizedQuestion || !normalizedAnswer) {
    return null;
  }

  return {
    question: normalizedQuestion,
    answer: normalizedAnswer,
  };
}

/**
 * Removes invalid and duplicate FAQ items while preserving author-provided order.
 */
export function normalizeFaqItems(items: readonly FaqItem[]): FaqItem[] {
  const seenQuestions = new Set<string>();
  const result: FaqItem[] = [];

  for (const item of items) {
    const normalizedItem = createFaqItem(item.question, item.answer);

    if (!normalizedItem) {
      continue;
    }

    const questionKey = normalizedItem.question.toLowerCase();

    if (seenQuestions.has(questionKey)) {
      continue;
    }

    seenQuestions.add(questionKey);
    result.push(normalizedItem);
  }

  return result;
}

/**
 * Filters FAQ items by a search query for reusable FAQ sections or page-specific selection.
 */
export function filterFaqItems(items: readonly FaqItem[], query: string): FaqItem[] {
  const normalizedQuery = normalizeFaqText(query).toLowerCase();

  if (!normalizedQuery) {
    return normalizeFaqItems(items);
  }

  return normalizeFaqItems(items).filter((item) => {
    const haystack = `${item.question} ${item.answer}`.toLowerCase();

    return haystack.includes(normalizedQuery);
  });
}

/**
 * Formats rent input as readable SEO copy without assuming a currency when one is already present.
 */
export function formatRentForFaq(rent?: string | number): string {
  if (rent === undefined || rent === null || rent === "") {
    return "current monthly rent";
  }

  if (typeof rent === "number") {
    return `Rs. ${rent.toLocaleString("en-IN")} per month`;
  }

  return normalizeFaqText(rent);
}

/**
 * Returns a readable amenities phrase for FAQ answers.
 */
export function formatAmenitiesForFaq(amenities: readonly string[] = []): string {
  const normalizedAmenities = [...new Set(amenities.map(normalizeFaqText).filter(Boolean))];

  if (normalizedAmenities.length === 0) {
    return "essential amenities";
  }

  if (normalizedAmenities.length === 1) {
    return normalizedAmenities[0] ?? "essential amenities";
  }

  return `${normalizedAmenities.slice(0, -1).join(", ")} and ${normalizedAmenities[normalizedAmenities.length - 1]}`;
}

/**
 * Generates deterministic, SEO-friendly FAQs for locality and property-type landing pages.
 */
export function generateSeoFaqs(input: SeoFaqGeneratorInput, options: SeoFaqGeneratorOptions = {}): FaqItem[] {
  const locality = normalizeFaqText(input.locality);
  const propertyType = normalizeFaqText(input.propertyType);
  const city = input.city ? normalizeFaqText(input.city) : "";
  const location = city ? `${locality}, ${city}` : locality;
  const brandName = input.brandName ? normalizeFaqText(input.brandName) : "MakeMyStay";
  const rent = formatRentForFaq(input.rent);
  const amenities = formatAmenitiesForFaq(input.amenities);
  const count = options.count ?? DEFAULT_FAQ_COUNT;

  const faqs = [
    createFaqItem(
      `Which is the best ${propertyType} in ${locality}?`,
      `The best ${propertyType} in ${location} depends on your budget, commute, room preference and amenities. ${brandName} helps you compare verified options with ${amenities}.`,
    ),
    createFaqItem(
      `What is the rent for ${propertyType} in ${locality}?`,
      `${propertyType} rent in ${location} usually depends on sharing type, building quality, food, amenities and distance from offices or colleges. A useful starting reference is ${rent}.`,
    ),
    createFaqItem(
      `Are there furnished ${propertyType} options in ${locality}?`,
      `Yes, furnished ${propertyType} options in ${location} commonly include beds, storage, WiFi and access to shared facilities. Check each listing for exact inclusions before booking.`,
    ),
    createFaqItem(
      `How do I find verified ${propertyType} in ${locality}?`,
      `You can find verified ${propertyType} in ${location} by comparing photos, amenities, rent, house rules, location and availability on ${brandName}.`,
    ),
    createFaqItem(
      `Is ${locality} good for ${propertyType} accommodation?`,
      `${locality} is a strong choice for ${propertyType} accommodation when it matches your office, college, transport and lifestyle needs. Compare commute time and amenities before finalizing.`,
    ),
    createFaqItem(
      `What amenities are available in ${propertyType} in ${locality}?`,
      `${propertyType} options in ${location} may include ${amenities}. Amenities vary by property, so always confirm what is included in the rent.`,
    ),
    createFaqItem(
      `Can I get single sharing ${propertyType} in ${locality}?`,
      `Single sharing ${propertyType} options may be available in ${location}, usually at a higher rent than double or triple sharing rooms. Availability changes by property and move-in date.`,
    ),
    createFaqItem(
      `Are there budget ${propertyType} options in ${locality}?`,
      `Budget ${propertyType} options in ${location} are available based on sharing type, room size and included services. Compare total monthly cost, not just base rent.`,
    ),
    createFaqItem(
      `Are there luxury ${propertyType} options in ${locality}?`,
      `Luxury ${propertyType} options in ${location} usually offer better interiors, larger rooms, premium amenities and improved common areas. Review photos and inclusions before booking.`,
    ),
    createFaqItem(
      `How can I book ${propertyType} in ${locality}?`,
      `You can shortlist ${propertyType} options in ${location}, compare rent and amenities, schedule a visit if needed and confirm availability through ${brandName}.`,
    ),
    createFaqItem(
      `What should I check before booking ${propertyType} in ${locality}?`,
      `Before booking ${propertyType} in ${location}, check rent, deposit, notice period, food, laundry, WiFi, visitor rules, security, commute and the exact amenities included.`,
    ),
    createFaqItem(
      `Is food included in ${propertyType} rent in ${locality}?`,
      `Food may or may not be included in ${propertyType} rent in ${location}. Always confirm meal plans, kitchen access and extra charges before booking.`,
    ),
    createFaqItem(
      `Is WiFi available in ${propertyType} in ${locality}?`,
      `Many ${propertyType} options in ${location} provide WiFi, but speed, data limits and backup connectivity can vary. Confirm details with the property before moving in.`,
    ),
    createFaqItem(
      `Are ${propertyType} options in ${locality} suitable for working professionals?`,
      `Yes, many ${propertyType} options in ${location} are suitable for working professionals, especially when they offer reliable WiFi, housekeeping, laundry and easy commute access.`,
    ),
    createFaqItem(
      `Are there ${propertyType} options near offices and metro in ${locality}?`,
      `${propertyType} options near offices, tech parks, colleges or metro access in ${locality} are often in higher demand. Compare location carefully to reduce commute time.`,
    ),
    createFaqItem(
      `What is the deposit for ${propertyType} in ${locality}?`,
      `Deposit for ${propertyType} in ${location} varies by property, rent, sharing type and stay duration. Confirm deposit, refund policy and deductions before paying.`,
    ),
    createFaqItem(
      `Can students find ${propertyType} in ${locality}?`,
      `Students can find ${propertyType} options in ${location} depending on budget, distance from college, food preference, safety and house rules.`,
    ),
  ].filter((faq): faq is FaqItem => Boolean(faq));

  return normalizeFaqItems(faqs).slice(0, count);
}

/**
 * Returns generated FAQs as a JSON string for API responses, static data files, or AI workflows.
 */
export function generateSeoFaqJson(input: SeoFaqGeneratorInput, options: SeoFaqGeneratorOptions = {}): string {
  return JSON.stringify(generateSeoFaqs(input, options), null, 2);
}
