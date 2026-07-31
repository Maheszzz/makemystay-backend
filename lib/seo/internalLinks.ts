export interface InternalLink {
  readonly label: string;
  readonly href: string;
  readonly priority?: number;
  readonly tags?: readonly string[];
}

export interface InternalLinkOptions {
  readonly currentPath?: string;
  readonly tags?: readonly string[];
  readonly limit?: number;
}

/**
 * Normalizes internal paths so matching and deduplication are consistent.
 */
export function normalizeInternalPath(path: string): string {
  if (!path) {
    return "/";
  }

  const pathWithoutHash = path.split("#")[0]?.split("?")[0] ?? path;
  const withLeadingSlash = pathWithoutHash.startsWith("/") ? pathWithoutHash : `/${pathWithoutHash}`;
  const withoutTrailingSlash = withLeadingSlash.length > 1 ? withLeadingSlash.replace(/\/+$/, "") : withLeadingSlash;

  return withoutTrailingSlash || "/";
}

/**
 * Returns true when an href points to a same-site relative route.
 */
export function isInternalHref(href: string): boolean {
  return href.startsWith("/") && !href.startsWith("//");
}

/**
 * Deduplicates internal links by normalized path while preserving the strongest priority.
 */
export function dedupeInternalLinks(links: readonly InternalLink[]): InternalLink[] {
  const byHref = new Map<string, InternalLink>();

  for (const link of links) {
    if (!isInternalHref(link.href)) {
      continue;
    }

    const normalizedHref = normalizeInternalPath(link.href);
    const existing = byHref.get(normalizedHref);

    if (!existing || (link.priority ?? 0) > (existing.priority ?? 0)) {
      byHref.set(normalizedHref, { ...link, href: normalizedHref });
    }
  }

  return [...byHref.values()];
}

/**
 * Selects relevant internal links using route exclusion, tag matching, priority, and a configurable limit.
 */
export function selectInternalLinks(links: readonly InternalLink[], options: InternalLinkOptions = {}): InternalLink[] {
  const currentPath = options.currentPath ? normalizeInternalPath(options.currentPath) : undefined;
  const requestedTags = new Set((options.tags ?? []).map((tag) => tag.toLowerCase()));

  return dedupeInternalLinks(links)
    .filter((link) => normalizeInternalPath(link.href) !== currentPath)
    .filter((link) => {
      if (requestedTags.size === 0) {
        return true;
      }

      return (link.tags ?? []).some((tag) => requestedTags.has(tag.toLowerCase()));
    })
    .sort((first, second) => (second.priority ?? 0) - (first.priority ?? 0) || first.label.localeCompare(second.label))
    .slice(0, options.limit);
}

/**
 * Builds a stable internal link object for use in navigation blocks, content modules, or schema.
 */
export function createInternalLink(label: string, href: string, options: Omit<InternalLink, "label" | "href"> = {}): InternalLink {
  return {
    ...options,
    label: label.trim(),
    href: normalizeInternalPath(href),
  };
}
