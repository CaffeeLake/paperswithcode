/**
 * Image preloading utility
 * Preloads images to ensure they're cached before rendering
 */

/**
 * Preloads an image and returns a Promise that resolves when the image is loaded
 * @param imageUrl - The URL of the image to preload
 * @returns Promise that resolves when the image is loaded (or fails gracefully)
 */
export const preloadImage = (imageUrl: string): Promise<void> => {
  return new Promise((resolve) => {
    // If no URL provided, resolve immediately
    if (!imageUrl) {
      resolve();
      return;
    }

    const img = new Image();

    // Resolve when image loads successfully
    img.onload = () => {
      console.log(`[ImagePreloader] Successfully preloaded: ${imageUrl}`);
      resolve();
    };

    // Also resolve on error to avoid blocking the UI
    img.onerror = (error) => {
      console.warn(`[ImagePreloader] Failed to preload image: ${imageUrl}`, error);
      resolve(); // Still resolve to avoid blocking
    };

    // Start loading the image
    img.src = imageUrl;
  });
};

/**
 * Preloads multiple images in parallel
 * @param imageUrls - Array of image URLs to preload
 * @returns Promise that resolves when all images are loaded (or failed)
 */
export const preloadImages = (imageUrls: string[]): Promise<void> => {
  const validUrls = imageUrls.filter(url => url && url.trim() !== '');

  if (validUrls.length === 0) {
    return Promise.resolve();
  }

  return Promise.all(validUrls.map(preloadImage)).then(() => {
    console.log(`[ImagePreloader] Preloaded ${validUrls.length} images`);
  });
};
