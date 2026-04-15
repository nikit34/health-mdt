"use client";

import { useEffect } from "react";
import { setSession } from "@/lib/api";

/**
 * Runs once on mount. If URL contains `?session=<token>` (OAuth callback redirect),
 * stores it in localStorage and strips it from the URL.
 */
export function SessionIntake() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const token = params.get("session");
    if (token) {
      setSession(token);
      params.delete("session");
      const newQs = params.toString();
      const newUrl = window.location.pathname + (newQs ? `?${newQs}` : "") + window.location.hash;
      window.history.replaceState({}, "", newUrl);
    }
  }, []);
  return null;
}
