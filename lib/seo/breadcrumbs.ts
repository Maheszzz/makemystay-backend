import { normalizeInternalPath } from "./internalLinks";

export interface BreadcrumbItem {
  readonly name: string;
  readonly href: string;
}

export interface BreadcrumbOptions {
  readonly homeLabel?: string;
  readonly baseUrl?: string;
  readonly labels?: Readonly<Record<string, string>>;
}

/**
 * Converts a URL segment into a human-readable breadcrumb label.
 */
export function segmentToBreadcrumbLabel(segment: string): string {
  return decodeURIComponent(segment)
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/**
 * Joins a base URL and relative path into an absolute canonical URL.
 */
export function toAbsoluteUrl(path: string, baseUrl?: string): string {
  const normalizedPath = normalizeInternalPath(path);

  if (!baseUrl) {
    return normalizedPath;
  }

  return new URL(normalizedPath, baseUrl).toString();
}

/**
 * Builds breadcrumb items from a path without requiring page-specific conditionals.
 */
export function buildBreadcrumbs(path: string, options: BreadcrumbOptions = {}): BreadcrumbItem[] {
  const normalizedPath = normalizeInternalPath(path);
  const segments = normalizedPath.split("/").filter(Boolean);
  const breadcrumbs: BreadcrumbItem[] = [
    {
      name: options.homeLabel ?? "Home",
      href: toAbsoluteUrl("/", options.baseUrl),
    },
  ];

  let currentPath = "";

  for (const segment of segments) {
    currentPath = `${currentPath}/${segment}`;
    breadcrumbs.push({
      name: options.labels?.[segment] ?? segmentToBreadcrumbLabel(segment),
      href: toAbsoluteUrl(currentPath, options.baseUrl),
    });
  }

  return breadcrumbs;
}

/**
 * Returns the final breadcrumb item, useful for generating page headings or schema names.
 */
export function getCurrentBreadcrumb(path: string, options: BreadcrumbOptions = {}): BreadcrumbItem {
  const breadcrumbs = buildBreadcrumbs(path, options);

  return breadcrumbs[breadcrumbs.length - 1] ?? { name: options.homeLabel ?? "Home", href: toAbsoluteUrl("/", options.baseUrl) };
}
