import { useCallback, useEffect, useRef, useState } from 'react';

interface UseIntersectionObserverOptions {
  threshold?: number;
  rootMargin?: string;
}

/**
 * Observe a single sentinel element and report whether it is currently
 * intersecting the viewport. Uses a callback ref so the observer attaches the
 * moment the sentinel mounts — even if it appears later than the hook itself
 * (e.g. after a paginated query finishes loading and replaces the skeleton
 * placeholder with the real list + sentinel).
 */
export function useIntersectionObserver(
  options: UseIntersectionObserverOptions = {},
) {
  const { threshold = 0, rootMargin = '0px' } = options;
  const [isIntersecting, setIsIntersecting] = useState(false);
  const observerRef = useRef<IntersectionObserver | null>(null);

  const targetRef = useCallback(
    (node: Element | null) => {
      if (observerRef.current) {
        observerRef.current.disconnect();
        observerRef.current = null;
      }
      if (!node) {
        setIsIntersecting(false);
        return;
      }
      const observer = new IntersectionObserver(
        ([entry]) => setIsIntersecting(entry.isIntersecting),
        { threshold, rootMargin },
      );
      observer.observe(node);
      observerRef.current = observer;
    },
    [threshold, rootMargin],
  );

  useEffect(
    () => () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
        observerRef.current = null;
      }
    },
    [],
  );

  return { targetRef, isIntersecting };
}
