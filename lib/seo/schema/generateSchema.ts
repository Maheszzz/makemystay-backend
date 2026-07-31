import { buildBreadcrumbSchema } from "./breadcrumb";
import { buildFaqSchema } from "./faq";
import { buildLocalBusinessSchema, type LocalBusinessSchemaInput } from "./localBusiness";
import { buildOrganizationSchema, type OrganizationSchemaInput } from "./organization";
import { buildPlaceSchema, type PlaceSchemaInput } from "./place";
import { buildResidenceSchema, type ResidenceSchemaInput } from "./residence";
import { buildSearchActionSchema } from "./searchAction";
import { buildSpeakableSchema, type SpeakableSchemaInput } from "./speakable";
import type { BreadcrumbSchemaItem, FaqSchemaItem, JsonLdObject, SearchActionInput } from "./types";
import { buildJsonLdGraph, compactJsonLd } from "./utils";
import { buildWebPageSchema, type WebPageSchemaInput } from "./webPage";
import { buildWebSiteSchema, type WebSiteSchemaInput } from "./webSite";

export interface GenerateSchemaInput {
  readonly organization?: OrganizationSchemaInput;
  readonly localBusiness?: LocalBusinessSchemaInput;
  readonly place?: PlaceSchemaInput;
  readonly residence?: ResidenceSchemaInput;
  readonly breadcrumb?: readonly BreadcrumbSchemaItem[];
  readonly faq?: readonly FaqSchemaItem[];
  readonly speakable?: SpeakableSchemaInput;
  readonly searchAction?: SearchActionInput;
  readonly webSite?: WebSiteSchemaInput;
  readonly webPage?: WebPageSchemaInput;
  readonly extraSchemas?: readonly JsonLdObject[];
}

/**
 * Generates one reusable JSON-LD graph from any supported schema inputs.
 */
export function generateSchema(input: GenerateSchemaInput): JsonLdObject {
  const speakable = input.speakable ? buildSpeakableSchema(input.speakable) : undefined;
  const schemas = [
    input.organization ? buildOrganizationSchema(input.organization) : undefined,
    input.webSite ? buildWebSiteSchema(input.webSite) : undefined,
    input.webPage ? buildWebPageSchema({ ...input.webPage, speakable: input.webPage.speakable ?? speakable }) : undefined,
    input.localBusiness ? buildLocalBusinessSchema(input.localBusiness) : undefined,
    input.place ? buildPlaceSchema(input.place) : undefined,
    input.residence ? buildResidenceSchema(input.residence) : undefined,
    input.breadcrumb ? buildBreadcrumbSchema(input.breadcrumb) : undefined,
    input.faq ? buildFaqSchema(input.faq) : undefined,
    input.searchAction ? buildSearchActionSchema(input.searchAction) : undefined,
    ...(input.extraSchemas ?? []),
  ].filter((schema): schema is JsonLdObject => Boolean(schema));

  return compactJsonLd(buildJsonLdGraph(schemas));
}
