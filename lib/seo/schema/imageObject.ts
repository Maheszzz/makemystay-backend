import type { JsonLdObject } from "./types";

export interface ImageObjectSchemaInput {
  readonly url: string;
  readonly name?: string;
  readonly caption?: string;
  readonly description?: string;
  readonly width?: number;
  readonly height?: number;
  readonly author?: string;
  readonly license?: string;
  readonly representativeOfPage?: boolean;
  readonly uploadDate?: string;
  readonly thumbnailUrl?: string;
}

export interface ImageGallerySchemaInput {
  readonly name: string;
  readonly description?: string;
  readonly url?: string;
  readonly images: readonly ImageObjectSchemaInput[];
}

/**
 * Builds an ImageObject JSON-LD schema compliant with Google Rich Results and Schema.org.
 */
export function buildImageObjectSchema(input: ImageObjectSchemaInput): JsonLdObject {
  const schema: Record<string, unknown> = {
    "@type": "ImageObject",
    url: input.url,
    contentUrl: input.url,
  };

  if (input.name?.trim()) {
    schema.name = input.name.trim();
  }
  if (input.caption?.trim()) {
    schema.caption = input.caption.trim();
  }
  if (input.description?.trim()) {
    schema.description = input.description.trim();
  }
  if (input.width && input.width > 0) {
    schema.width = input.width;
  }
  if (input.height && input.height > 0) {
    schema.height = input.height;
  }
  if (input.author?.trim()) {
    schema.author = {
      "@type": "Person",
      name: input.author.trim(),
    };
  }
  if (input.license?.trim()) {
    schema.license = input.license.trim();
  }
  if (input.representativeOfPage !== undefined) {
    schema.representativeOfPage = input.representativeOfPage;
  }
  if (input.uploadDate?.trim()) {
    schema.uploadDate = input.uploadDate.trim();
  }
  if (input.thumbnailUrl?.trim()) {
    schema.thumbnail = {
      "@type": "ImageObject",
      url: input.thumbnailUrl.trim(),
    };
  }

  return schema as JsonLdObject;
}

/**
 * Builds an ImageGallery or ItemList of ImageObjects JSON-LD schema for multi-image presentations.
 */
export function buildImageGallerySchema(input: ImageGallerySchemaInput): JsonLdObject {
  const itemListElement = input.images.map((img, idx) => ({
    "@type": "ListItem",
    position: idx + 1,
    item: buildImageObjectSchema(img),
  }));

  const schema: Record<string, unknown> = {
    "@type": "ImageGallery",
    name: input.name.trim(),
    numberOfItems: input.images.length,
    itemListElement,
  };

  if (input.description?.trim()) {
    schema.description = input.description.trim();
  }
  if (input.url?.trim()) {
    schema.url = input.url.trim();
  }

  return schema as JsonLdObject;
}
