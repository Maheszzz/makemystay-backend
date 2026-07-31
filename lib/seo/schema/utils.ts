import type { JsonLdObject, JsonLdValue } from "./types";

/**
 * Removes null, undefined, empty arrays, and empty objects from JSON-LD output.
 */
export function compactJsonLd<T extends JsonLdValue>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((item) => compactJsonLd(item)).filter((item) => item !== null && item !== undefined) as T;
  }

  if (value && typeof value === "object") {
    const entries = Object.entries(value)
      .map(([key, entryValue]) => [key, compactJsonLd(entryValue as JsonLdValue)] as const)
      .filter(([, entryValue]) => {
        if (entryValue === null || entryValue === undefined || entryValue === "") {
          return false;
        }

        if (Array.isArray(entryValue)) {
          return entryValue.length > 0;
        }

        if (typeof entryValue === "object") {
          return Object.keys(entryValue).length > 0;
        }

        return true;
      });

    return Object.fromEntries(entries) as T;
  }

  return value;
}

/**
 * Builds a schema.org @id value from a URL and stable fragment.
 */
export function buildSchemaId(url: string, fragment: string): string {
  return `${url.replace(/#.*$/, "")}#${fragment.replace(/^#+/, "")}`;
}

/**
 * Wraps one or more schema objects in a JSON-LD graph for one script tag.
 */
export function buildJsonLdGraph(items: readonly JsonLdObject[]): JsonLdObject {
  return compactJsonLd({
    "@context": "https://schema.org",
    "@graph": items,
  });
}

/**
 * Serializes JSON-LD safely for use inside an application/ld+json script tag.
 */
export function serializeJsonLd(schema: JsonLdObject): string {
  return JSON.stringify(schema).replace(/</g, "\\u003c");
}
