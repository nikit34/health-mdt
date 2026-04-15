// Thin API client — reads session token from localStorage.
// In production, NEXT_PUBLIC_API_URL is "/api" (Caddy routes to backend).
// In dev, it's also "/api" (Next.js rewrites to localhost:8000).

const BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

function sessionToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("hmdt_session") || "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Session", sessionToken());
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${BASE}${path}`, { ...init, headers, cache: "no-store" });
  if (res.status === 401) {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("hmdt_session");
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    throw new Error("unauthorized");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}

export const api = {
  status: () => request<{
    version: string;
    capabilities: { llm: boolean; oura: boolean; telegram: boolean };
    user_onboarded: boolean;
    counts: Record<string, number>;
    domain: string;
  }>("/status"),

  login: (pin: string) => request<{ token: string; mode: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ pin }),
  }),

  me: {
    get: () => request<any>("/data/me"),
    update: (body: any) => request<any>("/data/me", { method: "PUT", body: JSON.stringify(body) }),
  },

  checkin: {
    list: (limit = 50) => request<any[]>(`/data/checkins?limit=${limit}`),
    create: (body: { text: string; mood?: number; energy?: number; sleep_quality?: number; tags?: string[] }) =>
      request<any>("/data/checkin", { method: "POST", body: JSON.stringify(body) }),
  },

  metrics: (days = 30, kind?: string) =>
    request<{ series: Record<string, { ts: string; value: number; unit: string; source: string }[]>; count: number }>(
      `/data/metrics?days=${days}${kind ? `&kind=${kind}` : ""}`,
    ),

  reports: {
    briefLatest: () => request<any | null>("/reports/brief/latest"),
    briefGenerate: () => request<any>("/reports/brief/generate", { method: "POST" }),
    briefs: (limit = 30) => request<any[]>(`/reports/briefs?limit=${limit}`),
    mdtLatest: () => request<any | null>("/reports/mdt/latest"),
    mdtList: (limit = 10) => request<any[]>(`/reports/mdt?limit=${limit}`),
    mdtGet: (id: number) => request<any>(`/reports/mdt/${id}`),
    mdtRun: (body?: { kind?: string; window_days?: number }) =>
      request<any>(`/reports/mdt/run?kind=${body?.kind ?? "weekly"}&window_days=${body?.window_days ?? 7}`, {
        method: "POST",
      }),
    mdtPdf: async (id: number): Promise<void> => {
      const token = (typeof window !== "undefined" && window.localStorage.getItem("hmdt_session")) || "";
      const res = await fetch(`${BASE}/reports/mdt/${id}/pdf`, { headers: { "X-Session": token } });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `mdt-report-${id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    },
  },

  tasks: {
    list: (status: string | null = "open") =>
      request<any[]>(`/tasks${status ? `?status=${status}` : ""}`),
    create: (body: { title: string; detail?: string; priority?: string; due?: string }) =>
      request<any>("/tasks", { method: "POST", body: JSON.stringify(body) }),
    update: (id: number, body: any) =>
      request<any>(`/tasks/${id}`, { method: "PUT", body: JSON.stringify(body) }),
    delete: (id: number) => request<any>(`/tasks/${id}`, { method: "DELETE" }),
  },

  documents: {
    list: () => request<any[]>("/documents"),
    upload: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return request<any>("/documents/upload", { method: "POST", body: fd });
    },
  },

  sources: {
    ouraSync: () => request<any>("/sources/oura/sync", { method: "POST" }),
    appleHealthImport: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return request<any>("/sources/apple-health/import", { method: "POST", body: fd });
    },
  },

  chat: {
    ask: (question: string, window_days = 14) =>
      request<{ answer: string; confidence: number; safety_flags: string[]; follow_ups: string[] }>("/chat/ask", {
        method: "POST",
        body: JSON.stringify({ question, window_days }),
      }),
    streamAsk: (
      question: string,
      onChunk: (text: string) => void,
      onDone: () => void,
      onError: (err: string) => void,
      window_days = 14,
    ): (() => void) => {
      const params = new URLSearchParams({
        question,
        window_days: String(window_days),
        session: (typeof window !== "undefined" && window.localStorage.getItem("hmdt_session")) || "",
      });
      const url = `${BASE}/chat/ask/stream?${params.toString()}`;
      const source = new EventSource(url);
      source.addEventListener("start", () => {});
      source.addEventListener("chunk", (e: MessageEvent) => onChunk(e.data));
      source.addEventListener("done", () => {
        source.close();
        onDone();
      });
      source.addEventListener("error", (e: MessageEvent) => {
        source.close();
        onError(typeof e?.data === "string" ? e.data : "stream_error");
      });
      return () => source.close();
    },
  },
};

export function setSession(token: string) {
  if (typeof window !== "undefined") window.localStorage.setItem("hmdt_session", token);
}

export function clearSession() {
  if (typeof window !== "undefined") window.localStorage.removeItem("hmdt_session");
}

export function hasSession(): boolean {
  return !!sessionToken();
}
