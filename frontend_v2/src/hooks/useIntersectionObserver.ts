import { useEffect, useRef, useState } from 'react';

interface UseIntersectionObserverOptions {
  threshold?: number;
  rootMargin?: string;
}

export function useIntersectionObserver(
  options: UseIntersectionObserverOptions = {}
) {
  const { threshold = 0, rootMargin = '0px' } = options;
  const [isIntersecting, setIsIntersecting] = useState(false);
  const targetRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const target = targetRef.current;
    if (!target) {
      console.log('👁️ Intersection Observer: No target element found');
      return;
    }

    console.log('👁️ Intersection Observer: Setting up observer', { threshold, rootMargin });

    const observer = new IntersectionObserver(
      ([entry]) => {
        console.log('👁️ Intersection Observer:', {
          isIntersecting: entry.isIntersecting,
          intersectionRatio: entry.intersectionRatio,
          boundingClientRect: entry.boundingClientRect,
          rootBounds: entry.rootBounds,
          threshold,
          rootMargin
        });
        setIsIntersecting(entry.isIntersecting);
      },
      { threshold, rootMargin }
    );

    observer.observe(target);
    console.log('👁️ Intersection Observer: Started observing target');

    return () => {
      console.log('👁️ Intersection Observer: Cleaning up observer');
      observer.unobserve(target);
    };
  }, [threshold, rootMargin]);

  return { targetRef, isIntersecting };
}
