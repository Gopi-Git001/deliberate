import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

const THRESHOLD_PX = 140;

/** Smoothly follows new content while pinned to the bottom. Only an upward scroll by the
 *  user unpins — our own smooth scrolls (which pass through mid-positions while content
 *  keeps arriving) never do. Returning to the bottom re-pins. */
export function useAutoScroll(itemCount: number, resetKey: unknown) {
  const ref = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);
  const [unseen, setUnseen] = useState(0);
  const pinnedRef = useRef(true);
  const lastTop = useRef(0);
  const lastCount = useRef(itemCount);

  const setPin = (value: boolean) => {
    if (pinnedRef.current !== value) {
      pinnedRef.current = value;
      setPinned(value);
    }
    if (value) setUnseen(0);
  };

  const onScroll = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const fromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const movedUp = el.scrollTop < lastTop.current - 4;
    lastTop.current = el.scrollTop;
    if (fromBottom < THRESHOLD_PX) setPin(true);
    else if (movedUp) setPin(false);
  }, []);

  const scrollToBottom = (smooth: boolean) => {
    const el = ref.current;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth && !reduce ? "smooth" : "auto" });
  };

  const jumpToLatest = useCallback(() => {
    setPin(true);
    scrollToBottom(true);
  }, []);

  useLayoutEffect(() => {
    const added = itemCount - lastCount.current;
    lastCount.current = itemCount;
    if (added <= 0) return;
    if (pinnedRef.current) scrollToBottom(true);
    else setUnseen((n) => n + added);
  }, [itemCount]);

  // Keep following when the viewport shrinks (e.g. the conclusion panel expands).
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (pinnedRef.current) scrollToBottom(false);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // New run: follow from the start again.
  useEffect(() => {
    setPin(true);
    lastCount.current = 0;
    lastTop.current = 0;
  }, [resetKey]);

  return { ref, pinned, unseen, onScroll, jumpToLatest };
}
