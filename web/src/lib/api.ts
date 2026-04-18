// Thin API client — reads session token from localStorage.
// In production, NEXT_PUBLIC_API_URL is "/api" (Caddy routes to backend).
// In dev, it's also "/api" (Next.js rewrites to localhost:8000).

const BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

function sessionToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("hmdt_session") || "";
}

async function request<T>(path: string, init: RequestInit = {}, opts: { publicRoute?: boolean } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!opts.publicRoute) headers.set("X-Session", sessionToken());
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${BASE}${path}`, { ...init, headers, cache: "no-store" });
  if (res.status === 401 && !opts.publicRoute) {
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
    capabilities: { llm: boolean; withings: boolean; telegram: boolean };
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

  medications: {
    list: (include_stopped = false) =>
      request<{
        id: number;
        name: string;
        dose: string;
        frequency: string;
        started_on: string | null;
        stopped_on: string | null;
        notes: string;
        reminder_time: string | null;
        is_active: boolean;
      }[]>(`/medications?include_stopped=${include_stopped}`),
    create: (body: {
      name: string;
      dose?: string;
      frequency?: string;
      started_on?: string;
      stopped_on?: string;
      notes?: string;
      reminder_time?: string;
    }) => request<any>("/medications", { method: "POST", body: JSON.stringify(body) }),
    update: (id: number, body: any) =>
      request<any>(`/medications/${id}`, { method: "PUT", body: JSON.stringify(body) }),
    delete: (id: number) => request<any>(`/medications/${id}`, { method: "DELETE" }),
  },

  sources: {
    appleHealthImport: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return request<any>("/sources/apple-health/import", { method: "POST", body: fd });
    },
  },

  withings: {
    status: () =>
      request<{
        app_configured: boolean;
        connected: boolean;
        expires_at: string | null;
        last_sync_at: string | null;
      }>("/sources/withings/status"),
    connect: () => request<{ authorize_url: string }>("/sources/withings/connect"),
    sync: () => request<any>("/sources/withings/sync", { method: "POST" }),
    disconnect: () => request<{ ok: boolean }>("/sources/withings/disconnect", { method: "DELETE" }),
  },

  telegram: {
    status: () => request<{ paired: boolean; chat_id: number | null; bot_configured: boolean }>("/telegram/status"),
    pairCode: () => request<{ code: string; ttl_seconds: number }>("/telegram/pair-code", { method: "POST" }),
    invite: () => request<{ url: string; bot_username: string; code: string; ttl_seconds: number }>("/telegram/invite", { method: "POST" }),
    unpair: () => request<{ ok: boolean }>("/telegram/unpair", { method: "DELETE" }),
  },

  push: {
    vapidKey: () => request<{ public_key: string }>("/push/vapid-key"),
    subscribe: (sub: { endpoint: string; p256dh: string; auth: string }) =>
      request<{ ok: boolean }>("/push/subscribe", {
        method: "POST",
        body: JSON.stringify({ ...sub, user_agent: navigator.userAgent }),
      }),
    unsubscribe: () => request<{ ok: boolean }>("/push/subscribe", { method: "DELETE" }),
    status: () => request<{ enabled: boolean; subscriptions: number }>("/push/status"),
  },

  public: {
    demoReport: () =>
      request<{
        id: number;
        created_at: string;
        kind: string;
        gp_synthesis: string;
        problem_list: { problem: string; status: string; since?: string; note?: string }[];
        safety_net: string[];
        specialist_notes: Record<string, {
          role: string;
          narrative?: string;
          soap?: { subjective?: string; objective?: string; assessment?: string; plan?: string };
          recommendations?: { title: string; detail?: string; priority?: string }[];
          safety_flags?: string[];
          evidence_pmids?: string[];
        }>;
        evidence: { pmid: string; title: string; journal: string; year: number | null; url: string }[];
        patient: { age: number | null; sex: string | null; context: string };
      }>("/public/demo-report", {}, { publicRoute: true }),
    waitlist: (email: string, tier = "", note = "") =>
      request<{ status: "ok" | "already_on_list" }>("/public/waitlist", {
        method: "POST",
        body: JSON.stringify({ email, tier, note }),
      }, { publicRoute: true }),
  },

  chat: {
    ask: (question: string, opts: { window_days?: number; conversation_id?: number } = {}) =>
      request<{
        conversation_id: number;
        answer: string;
        confidence: number;
        safety_flags: string[];
        follow_ups: string[];
      }>("/chat/ask", {
        method: "POST",
        body: JSON.stringify({
          question,
          window_days: opts.window_days ?? 14,
          conversation_id: opts.conversation_id ?? null,
        }),
      }),
    streamAsk: (
      question: string,
      onStart: (conversation_id: number) => void,
      onChunk: (text: string) => void,
      onDone: () => void,
      onError: (err: string) => void,
      opts: { window_days?: number; conversation_id?: number } = {},
    ): (() => void) => {
      const params = new URLSearchParams({
        question,
        window_days: String(opts.window_days ?? 14),
        session: (typeof window !== "undefined" && window.localStorage.getItem("hmdt_session")) || "",
      });
      if (opts.conversation_id) params.set("conversation_id", String(opts.conversation_id));
      const url = `${BASE}/chat/ask/stream?${params.toString()}`;
      const source = new EventSource(url);
      source.addEventListener("start", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          if (data.conversation_id) onStart(data.conversation_id);
        } catch {
          /* ignore */
        }
      });
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
    conversations: {
      list: () => request<{ id: number; title: string; updated_at: string }[]>("/chat/conversations"),
      get: (id: number) =>
        request<{
          id: number;
          title: string;
          updated_at: string;
          messages: {
            id: number;
            role: "user" | "assistant";
            content: string;
            meta: { safety_flags?: string[]; follow_ups?: string[]; confidence?: number; partial?: boolean };
            created_at: string;
          }[];
        }>(`/chat/conversations/${id}`),
      archive: (id: number) => request<{ ok: boolean }>(`/chat/conversations/${id}`, { method: "DELETE" }),
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
