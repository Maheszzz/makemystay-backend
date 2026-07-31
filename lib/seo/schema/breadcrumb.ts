import type { BreadcrumbSchemaItem, JsonLdObject } from "./types";
import { compactJsonLd } from "./utils";

/**
 * Builds BreadcrumbList schema from reusable breadcrumb items.
 */
export function buildBreadcrumbSchema(items: readonly BreadcrumbSchemaItem[]): JsonLdObject {
  return compactJsonLd({
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: item.href,
    })),
  });
}
