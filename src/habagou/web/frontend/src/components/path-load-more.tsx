import { useEffect, useRef } from "react";

// Footer hint that doubles as the infinite-scroll trigger: when it scrolls into
// view (and there is more to fetch), it calls onLoadMore via IntersectionObserver.

export function PathLoadMore({
  hasMore,
  isFetching,
  onLoadMore,
}: {
  hasMore: boolean;
  isFetching: boolean;
  onLoadMore: () => void;
}) {
  const ref = useRef<HTMLParagraphElement | null>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node || !hasMore || typeof IntersectionObserver === "undefined") {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting) && !isFetching) {
          onLoadMore();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, isFetching, onLoadMore]);

  return (
    <p className="py-8 text-center text-xs text-mist/80" data-testid="path-load-more" ref={ref}>
      ⋯ the path keeps generating as you go
    </p>
  );
}
