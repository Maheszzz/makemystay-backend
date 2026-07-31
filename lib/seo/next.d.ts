declare module "next" {
  export type Metadata = {
    title?:
      | string
      | {
          default: string;
          template?: string;
          absolute?: string;
        }
      | null;
    description?: string | null;
    keywords?: string | readonly string[] | null;
    openGraph?: {
      title?: string;
      description?: string;
      url?: string;
      siteName?: string;
      images?:
        | string
        | readonly string[]
        | readonly {
            url: string;
            width?: number;
            height?: number;
            alt?: string;
          }[];
      locale?: string;
      type?: string;
      publishedTime?: string;
      authors?: readonly string[];
      [key: string]: unknown;
    } | null;
    twitter?: {
      card?: string;
      title?: string;
      description?: string;
      images?: string | readonly string[];
      [key: string]: unknown;
    } | null;
    alternates?: {
      canonical?: string | null;
      languages?: Record<string, string>;
      [key: string]: unknown;
    } | null;
    robots?:
      | string
      | {
          index?: boolean;
          follow?: boolean;
          googleBot?:
            | string
            | {
                index?: boolean;
                follow?: boolean;
                "max-video-preview"?: number | string;
                "max-image-preview"?: string;
                "max-snippet"?: number | string;
                [key: string]: unknown;
              };
          [key: string]: unknown;
        }
      | null;
    [key: string]: unknown;
  };

  export namespace MetadataRoute {
    export type Sitemap = Array<{
      url: string;
      lastModified?: string | Date;
      changeFrequency?:
        | "always"
        | "hourly"
        | "daily"
        | "weekly"
        | "monthly"
        | "yearly"
        | "never";
      priority?: number;
      [key: string]: unknown;
    }>;
  }
}
