import type { FaqSchemaItem, JsonLdObject } from "./types";
import { compactJsonLd } from "./utils";

/**
 * Builds FAQPage schema from validated FAQ items.
 */
export function buildFaqSchema(items: readonly FaqSchemaItem[]): JsonLdObject | null {
  if (items.length === 0) {
    return null;
  }

  return compactJsonLd({
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: item.answer,
      },
    })),
  });
}
