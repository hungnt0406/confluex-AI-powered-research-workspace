"use client";

import { useEffect } from "react";

export function useRevealOnScroll() {
  useEffect(() => {
    if (typeof window === "undefined") return;

    const root = document.querySelector(".landing-root") as HTMLElement | null;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const targets = Array.from(
      (root ?? document).querySelectorAll<HTMLElement>("[data-reveal]"),
    );
    if (targets.length === 0) return;

    if (reduceMotion) {
      targets.forEach((el) => el.classList.add("is-revealed"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-revealed");
            observer.unobserve(entry.target);
          }
        }
      },
      { root: root ?? null, threshold: 0.12, rootMargin: "0px 0px -8% 0px" },
    );

    targets.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);
}
