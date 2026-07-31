import { type FaqItem, generateSeoFaqs, normalizeFaqItems, normalizeFaqText } from "./faq";

export type LocalityContentSectionId =
  | "hero"
  | "quickAnswer"
  | "aboutArea"
  | "rentalGuide"
  | "techParks"
  | "metro"
  | "hospitals"
  | "colleges"
  | "amenities"
  | "whoShouldStay"
  | "nearbyAreas"
  | "faqs"
  | "reviews";

export interface LocalityPointOfInterest {
  readonly name: string;
  readonly distance?: string;
  readonly description?: string;
}

export interface LocalityReviewSummary {
  readonly averageRating?: number;
  readonly reviewCount?: number;
  readonly highlights?: readonly string[];
}

export interface LocalityContentInput {
  readonly locality: string;
  readonly city: string;
  readonly propertyType: string;
  readonly primaryKeyword?: string;
  readonly secondaryKeywords?: readonly string[];
  readonly amenities?: readonly string[];
  readonly rent?: string | number;
  readonly rentRange?: string;
  readonly techParks?: readonly LocalityPointOfInterest[];
  readonly metroStations?: readonly LocalityPointOfInterest[];
  readonly hospitals?: readonly LocalityPointOfInterest[];
  readonly colleges?: readonly LocalityPointOfInterest[];
  readonly nearbyAreas?: readonly LocalityPointOfInterest[];
  readonly idealFor?: readonly string[];
  readonly reviews?: LocalityReviewSummary;
  readonly faqs?: readonly FaqItem[];
  readonly brandName?: string;
}

export interface LocalityContentOptions {
  readonly minimumWords?: number;
  readonly faqCount?: number;
}

export interface LocalityContentSection {
  readonly id: LocalityContentSectionId;
  readonly heading: string;
  readonly paragraphs: readonly string[];
  readonly faqs?: readonly FaqItem[];
}

export interface LocalityContentResult {
  readonly locality: string;
  readonly city: string;
  readonly wordCount: number;
  readonly sections: readonly LocalityContentSection[];
}

const DEFAULT_MINIMUM_WORDS = 2000;

/**
 * Counts words in generated locality content using whitespace tokenization.
 */
export function countWords(value: string): number {
  return normalizeFaqText(value).split(/\s+/).filter(Boolean).length;
}

/**
 * Formats rent for locality copy without assuming the caller always passes a number.
 */
export function formatLocalityRent(rent?: string | number, rentRange?: string): string {
  if (rentRange) {
    return normalizeFaqText(rentRange);
  }

  if (typeof rent === "number") {
    return `Rs. ${rent.toLocaleString("en-IN")} per month`;
  }

  if (typeof rent === "string" && rent.trim()) {
    return normalizeFaqText(rent);
  }

  return "the latest available monthly rent";
}

/**
 * Joins names into readable copy while keeping empty inputs harmless.
 */
export function joinNames(items: readonly string[], fallback: string): string {
  const names = [...new Set(items.map(normalizeFaqText).filter(Boolean))];

  if (names.length === 0) {
    return fallback;
  }

  if (names.length === 1) {
    return names[0] ?? fallback;
  }

  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/**
 * Converts points of interest into a compact sentence-friendly list.
 */
export function summarizePoints(items: readonly LocalityPointOfInterest[] = [], fallback: string): string {
  const names = items.map((item) => {
    const name = normalizeFaqText(item.name);
    const distance = item.distance ? ` (${normalizeFaqText(item.distance)})` : "";

    return `${name}${distance}`;
  });

  return joinNames(names, fallback);
}

/**
 * Normalizes paragraph text for duplicate detection.
 */
export function normalizeParagraphKey(paragraph: string): string {
  return normalizeFaqText(paragraph).toLowerCase();
}

/**
 * Removes duplicate paragraphs across all sections while preserving section order.
 */
export function dedupeLocalitySections(sections: readonly LocalityContentSection[]): LocalityContentSection[] {
  const seenParagraphs = new Set<string>();

  return sections.map((section) => {
    const paragraphs = section.paragraphs.filter((paragraph) => {
      const key = normalizeParagraphKey(paragraph);

      if (!key || seenParagraphs.has(key)) {
        return false;
      }

      seenParagraphs.add(key);
      return true;
    });

    return {
      ...section,
      paragraphs,
      faqs: section.faqs ? normalizeFaqItems(section.faqs) : undefined,
    };
  });
}

/**
 * Serializes all non-FAQ paragraphs for word-count and export workflows.
 */
export function localityContentToText(sections: readonly LocalityContentSection[]): string {
  return sections
    .flatMap((section) => [
      section.heading,
      ...section.paragraphs,
      ...(section.faqs ?? []).flatMap((faq) => [faq.question, faq.answer]),
    ])
    .join("\n\n");
}

/**
 * Builds the base section set from locality data without hardcoded page-specific logic.
 */
export function buildLocalitySections(input: LocalityContentInput, options: LocalityContentOptions = {}): LocalityContentSection[] {
  const locality = normalizeFaqText(input.locality);
  const city = normalizeFaqText(input.city);
  const propertyType = normalizeFaqText(input.propertyType);
  const brandName = input.brandName ? normalizeFaqText(input.brandName) : "MakeMyStay";
  const keyword = input.primaryKeyword ?? `${propertyType} in ${locality}`;
  const secondaryKeywords = joinNames(input.secondaryKeywords ?? [], `${propertyType} rent, furnished rooms and verified stays`);
  const rent = formatLocalityRent(input.rent, input.rentRange);
  const amenities = joinNames(input.amenities ?? [], "WiFi, food, housekeeping, laundry and security");
  const techParks = summarizePoints(input.techParks, "major office corridors and business hubs");
  const metroStations = summarizePoints(input.metroStations, "nearby metro and public transport points");
  const hospitals = summarizePoints(input.hospitals, "nearby hospitals and clinics");
  const colleges = summarizePoints(input.colleges, "nearby colleges and training institutes");
  const nearbyAreas = summarizePoints(input.nearbyAreas, "well-connected nearby areas");
  const idealFor = joinNames(input.idealFor ?? ["students", "working professionals", "new city movers"], "students and working professionals");
  const reviewHighlights = joinNames(input.reviews?.highlights ?? [], "location convenience, cleanliness, service quality and value for money");
  const ratingText =
    input.reviews?.averageRating && input.reviews?.reviewCount
      ? `${input.reviews.averageRating} from ${input.reviews.reviewCount} reviews`
      : "verified resident feedback";
  const faqs = input.faqs
    ? normalizeFaqItems(input.faqs).slice(0, options.faqCount ?? 15)
    : generateSeoFaqs(
        {
          locality,
          city,
          propertyType,
          amenities: input.amenities,
          rent: input.rentRange ?? input.rent,
          brandName,
        },
        { count: options.faqCount ?? 15 },
      );

  return [
    {
      id: "hero",
      heading: `${keyword} for rent in ${city}`,
      paragraphs: [
        `${keyword} is a high-intent search for people who want a practical stay option in ${locality}, ${city} without spending days comparing scattered listings. A strong locality page should explain rent, commute, amenities, nearby offices, transport access and resident fit in one place, because these are the signals users check before booking a ${propertyType}.`,
        `${brandName} positions ${locality} as a decision-ready rental market by combining verified stay information with helpful local context. Related searches such as ${secondaryKeywords} should be answered naturally so users understand whether ${locality} fits their work location, study needs, lifestyle, monthly budget and move-in timeline.`,
      ],
    },
    {
      id: "quickAnswer",
      heading: `Quick answer about ${propertyType} in ${locality}`,
      paragraphs: [
        `The short answer is that ${locality} is suitable for people looking for ${propertyType} accommodation with access to ${amenities}. Rent can vary by sharing type, room quality, food plan, furnishing, building age and distance from transit or employment hubs. A useful current reference is ${rent}.`,
        `If your priority is a shorter commute, start by checking properties closer to ${techParks} or ${metroStations}. If your priority is comfort, compare room size, meal quality, housekeeping frequency, laundry support, security, power backup and the rules for visitors, notice period and deposits.`,
      ],
    },
    {
      id: "aboutArea",
      heading: `About ${locality}`,
      paragraphs: [
        `${locality} is one of the locality clusters in ${city} where rental demand is shaped by employment access, education, transport and daily convenience. People usually search for ${keyword} when they want a managed stay that is easier to move into than an unfurnished flat and more predictable than informal rentals.`,
        `The area works well for ${idealFor} because it gives residents a balance of commute options, food choices, services and social infrastructure. Before selecting a stay, users should look beyond the listing photos and understand the surrounding roads, peak-hour travel time, nearby stores, medical access and the overall safety of the immediate lane or street.`,
      ],
    },
    {
      id: "rentalGuide",
      heading: `Rental guide for ${locality}`,
      paragraphs: [
        `Rent for ${propertyType} in ${locality} is influenced by room sharing, attached bathroom availability, furnishing, meals, air conditioning, location, maintenance standards and included services. The same locality can have budget, mid-range and premium options, so comparing total monthly cost is more useful than comparing only headline rent.`,
        `A practical rental checklist should include monthly rent, security deposit, lock-in period, notice period, electricity charges, food charges, laundry terms, WiFi reliability, cleaning schedule and refund rules. Users should also confirm whether the quoted rent applies to single sharing, double sharing or triple sharing rooms.`,
        `For SEO and user experience, a locality page should make pricing guidance honest and flexible. Instead of promising one fixed price, the content should explain why rent changes and what users receive at each budget level. This approach builds trust and reduces poor-quality leads from people with mismatched expectations.`,
      ],
    },
    {
      id: "techParks",
      heading: `Tech parks and office access near ${locality}`,
      paragraphs: [
        `Many users choose ${propertyType} in ${locality} because of access to ${techParks}. Office proximity can reduce commute fatigue, transport cost and late-night travel stress, especially for people working hybrid shifts or long office hours.`,
        `When comparing stays near tech parks, users should check actual commute time rather than only map distance. Traffic signals, road width, bus frequency, last-mile connectivity and availability of cabs or autos can change the practical value of a location. A property that is slightly farther away but better connected can sometimes be the smarter choice.`,
      ],
    },
    {
      id: "metro",
      heading: `Metro and transport access in ${locality}`,
      paragraphs: [
        `Metro and public transport access around ${locality} can make a major difference for daily travel. Useful access points include ${metroStations}. Residents who rely on public transport should check walking distance, feeder options, late-evening safety and the ease of reaching offices or colleges during peak hours.`,
        `Transport convenience is especially important for people who are new to ${city}. A well-connected ${propertyType} can reduce dependency on private vehicles and make weekend travel, office travel and emergency trips more manageable.`,
      ],
    },
    {
      id: "hospitals",
      heading: `Hospitals and healthcare near ${locality}`,
      paragraphs: [
        `Healthcare access is an important trust factor for any rental decision. Around ${locality}, residents may consider access to ${hospitals}. Even when a user is focused on rent or amenities, nearby medical support adds practical confidence for long-term stays.`,
        `People moving into a ${propertyType} should check how quickly they can reach a clinic, pharmacy or hospital, especially if they work late shifts, live away from family or are new to the city. This information helps the locality page feel complete rather than purely promotional.`,
      ],
    },
    {
      id: "colleges",
      heading: `Colleges and student access near ${locality}`,
      paragraphs: [
        `${locality} can also be relevant for students when colleges, coaching centers or training institutes are accessible. Important education points include ${colleges}. Student renters usually care about budget, food, study environment, safety, WiFi and predictable house rules.`,
        `For students, the best ${propertyType} is not always the cheapest option. A good stay should support study routines, provide reliable internet, maintain cleanliness and offer easy access to daily needs. Parents and students often value verified information because it lowers uncertainty before move-in.`,
      ],
    },
    {
      id: "amenities",
      heading: `Amenities to expect in ${locality}`,
      paragraphs: [
        `Common amenities in ${propertyType} options around ${locality} may include ${amenities}. Amenity quality matters as much as amenity availability, so users should check frequency, limits and real resident feedback before booking.`,
        `A helpful locality page should separate must-have amenities from nice-to-have amenities. WiFi, security, clean bathrooms, drinking water, power backup, laundry support and housekeeping usually affect daily comfort more than decorative features. Premium options may add better interiors, common lounges, air-conditioned rooms or app-based support.`,
      ],
    },
    {
      id: "whoShouldStay",
      heading: `Who should stay in ${locality}`,
      paragraphs: [
        `${locality} is a good fit for ${idealFor} when their commute, budget and lifestyle needs match the available properties. Working professionals may prioritize office access and quiet rooms, while students may prioritize affordability, food quality and study-friendly spaces.`,
        `New movers to ${city} may prefer managed ${propertyType} accommodation because it reduces setup work. Instead of arranging furniture, internet, cleaning and utilities separately, residents can move into a ready space and focus on work, classes or settling into the city.`,
      ],
    },
    {
      id: "nearbyAreas",
      heading: `Nearby areas to compare with ${locality}`,
      paragraphs: [
        `Users searching in ${locality} should also compare nearby areas such as ${nearbyAreas}. Nearby comparisons help users understand whether they are paying for location convenience, property quality, larger rooms or better amenities.`,
        `A nearby area may offer lower rent but longer commute, while ${locality} may offer better access to offices, colleges, hospitals or metro routes. The best choice depends on total monthly cost, travel time and how often the resident needs to commute.`,
      ],
    },
    {
      id: "faqs",
      heading: `FAQs about ${propertyType} in ${locality}`,
      paragraphs: [
        `These FAQs answer common Google searches about ${keyword}, including rent, amenities, booking, food, WiFi, deposit, students, professionals and commute. They are designed to help users make a faster and more confident rental decision.`,
      ],
      faqs,
    },
    {
      id: "reviews",
      heading: `Reviews and resident feedback for ${locality}`,
      paragraphs: [
        `Reviews for ${propertyType} options in ${locality} should be read for patterns rather than isolated comments. Useful signals include ${reviewHighlights}. The current review summary can be represented as ${ratingText} when verified data is available.`,
        `Good review content helps users validate whether the listing experience matches day-to-day reality. Cleanliness, staff response, food consistency, WiFi uptime, safety and refund transparency are often more useful than generic praise. A production locality page should keep review summaries factual, current and connected to real property data.`,
      ],
    },
  ];
}

/**
 * Adds unique expansion paragraphs until the content reaches the minimum word count.
 */
export function expandLocalityContentToMinimumWords(
  sections: readonly LocalityContentSection[],
  input: LocalityContentInput,
  minimumWords: number,
): LocalityContentSection[] {
  const locality = normalizeFaqText(input.locality);
  const city = normalizeFaqText(input.city);
  const propertyType = normalizeFaqText(input.propertyType);
  const rent = formatLocalityRent(input.rent, input.rentRange);
  const amenities = joinNames(input.amenities ?? [], "WiFi, meals, housekeeping, laundry and security");
  const expandedSections = sections.map((section) => ({ ...section, paragraphs: [...section.paragraphs] }));
  const seenParagraphs = new Set(expandedSections.flatMap((section) => section.paragraphs.map(normalizeParagraphKey)));
  const expansionParagraphs = [
    `For users comparing ${propertyType} options in ${locality}, the most reliable decision comes from matching three things: commute, monthly cost and living comfort. A listing may look attractive because of photos or a low rent, but the better question is whether it supports daily routines for work, study, meals, laundry, cleaning and rest.`,
    `Search behavior for ${locality}, ${city} shows that people want direct answers before they speak to a property manager. They look for rent, room sharing, food, WiFi, safety, distance from offices, nearby metro access and whether the stay is suitable for students or working professionals.`,
    `A production-ready locality page should avoid thin content by explaining the full rental context. That includes how deposits work, what amenities are usually included, what can cost extra, how to compare neighborhoods and why verified information matters before a user schedules a visit or pays an advance.`,
    `The strongest ${propertyType} pages are useful even before inventory is shown. They help a user understand whether ${locality} is the right area, what budget to prepare, what trade-offs to expect and which questions to ask before finalizing a room.`,
    `Amenities such as ${amenities} should be described with practical detail because users care about reliability. WiFi is useful only when stable, food is valuable only when consistent, and housekeeping matters most when it is frequent enough for shared living spaces.`,
    `Rent guidance for ${locality} should stay flexible because prices can change with demand, season, room type and property quality. A reference such as ${rent} helps users plan, while transparent comparison points help them understand why one stay may cost more than another.`,
    `Locality content should also support internal linking. Nearby areas, tech parks, metro stations, colleges and hospitals can connect users to more specific pages while helping search engines understand the relationship between ${locality} and surrounding demand centers.`,
    `For MakeMyStay, the content should guide users toward a confident action without exaggeration. Clear copy about availability, rent, amenities, commute and resident fit is more durable for SEO than keyword stuffing or repeated claims that do not add new information.`,
  ];

  let expansionIndex = 0;

  while (countWords(localityContentToText(expandedSections)) < minimumWords && expansionIndex < 120) {
    const targetSection = expandedSections[expansionIndex % expandedSections.length];
    const paragraph = expansionParagraphs[expansionIndex % expansionParagraphs.length];
    const cycle = Math.floor(expansionIndex / expansionParagraphs.length);
    const variant =
      cycle === 0
        ? paragraph
        : `${paragraph} For comparison set ${cycle}, this point is especially relevant when users compare ${locality} with other parts of ${city} before choosing a stay.`;
    const key = normalizeParagraphKey(variant);

    if (targetSection && !seenParagraphs.has(key)) {
      targetSection.paragraphs.push(variant);
      seenParagraphs.add(key);
    }

    expansionIndex += 1;
  }

  return dedupeLocalitySections(expandedSections);
}

/**
 * Generates complete locality content with all required sections and a minimum word count.
 */
export function generateLocalityContent(
  input: LocalityContentInput,
  options: LocalityContentOptions = {},
): LocalityContentResult {
  const minimumWords = options.minimumWords ?? DEFAULT_MINIMUM_WORDS;
  const baseSections = dedupeLocalitySections(buildLocalitySections(input, options));
  const sections = expandLocalityContentToMinimumWords(baseSections, input, minimumWords);
  const wordCount = countWords(localityContentToText(sections));

  return {
    locality: normalizeFaqText(input.locality),
    city: normalizeFaqText(input.city),
    wordCount,
    sections,
  };
}

/**
 * Returns locality content as formatted JSON for AI, APIs, or static generation pipelines.
 */
export function generateLocalityContentJson(
  input: LocalityContentInput,
  options: LocalityContentOptions = {},
): string {
  return JSON.stringify(generateLocalityContent(input, options), null, 2);
}
