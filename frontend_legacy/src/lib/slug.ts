/**
 * Utility functions for generating URL-friendly slugs.
 *
 * This matches the backend slug generation logic.
 */

/**
 * Convert text to a URL-friendly slug.
 *
 * - Converts to lowercase
 * - Replaces spaces and special characters with hyphens
 * - Removes consecutive hyphens
 * - Strips leading/trailing hyphens
 *
 * @example
 * slugify("Vision Transformer") // "vision-transformer"
 * slugify("GPT-2") // "gpt-2"
 * slugify("Adam Optimizer") // "adam-optimizer"
 *
 * @param text - The text to slugify
 * @returns URL-friendly slug
 */
export function slugify(text: string): string {
  if (!text) return "";

  return text
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '') // Remove diacritics
    .replace(/[^a-z0-9]+/g, '-')     // Replace non-alphanumeric with hyphens
    .replace(/-+/g, '-')              // Remove consecutive hyphens
    .replace(/^-|-$/g, '');           // Strip leading/trailing hyphens
}

/**
 * Get the method slug from a method object or name.
 * Prefers the slug field if available, otherwise generates one.
 *
 * @param method - Method object with optional slug field, or method name string
 * @returns URL-friendly slug
 */
export function getMethodSlug(method: { slug?: string; name: string } | string): string {
  if (typeof method === 'string') {
    return slugify(method);
  }
  return method.slug || slugify(method.name);
}
