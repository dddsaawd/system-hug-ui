import { z } from "zod";

// Validation schemas
export const startEngineSchema = z.object({
  target_url: z.string().trim().url({ message: "URL inválida" }).max(2048, { message: "URL muito longa" }),
  proxies: z.array(z.string().trim().min(1)).min(1, { message: "Adicione pelo menos 1 proxy" }),
  interval_seconds: z.number().min(1).max(3600).default(120),
  max_retries: z.number().min(1).max(100).default(5),
  cpfs: z.array(z.string().trim()).optional(),
});

export type StartEnginePayload = z.infer<typeof startEngineSchema>;

export interface EngineStatus {
  id: string;
  status: "running" | "stopped" | "error";
  successes: number;
  failures: number;
  total_attempts: number;
  uptime_seconds: number;
  logs: { timestamp: string; message: string; type: "success" | "error" | "info" }[];
}

// Get saved config from localStorage
function getConfig(): { baseUrl: string; token: string } {
  const saved = localStorage.getItem("phantom_engine_config");
  if (saved) {
    try {
      return JSON.parse(saved);
    } catch {
      // fall through
    }
  }
  return { baseUrl: "", token: "" };
}

export function saveEngineConfig(baseUrl: string, token: string) {
  localStorage.setItem(
    "phantom_engine_config",
    JSON.stringify({ baseUrl: baseUrl.replace(/\/+$/, ""), token })
  );
}

export function getEngineConfig() {
  return getConfig();
}

async function apiCall<T>(
  method: "GET" | "POST",
  path: string,
  body?: unknown
): Promise<T> {
  const { baseUrl, token } = getConfig();

  if (!baseUrl) throw new Error("URL base da API não configurada. Vá em Configurações.");
  if (!token) throw new Error("Token de autenticação não configurado. Vá em Configurações.");

  const url = `${baseUrl}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };

  const res = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const errorText = await res.text().catch(() => "Erro desconhecido");
    throw new Error(`API Error ${res.status}: ${errorText}`);
  }

  return res.json();
}

export async function startEngine(payload: StartEnginePayload): Promise<{ id: string }> {
  // Validate payload before sending
  const validated = startEngineSchema.parse(payload);
  return apiCall<{ id: string }>("POST", "/api/start", validated);
}

export async function getEngineStatus(id: string): Promise<EngineStatus> {
  if (!id || id.length > 100) throw new Error("ID de sessão inválido");
  return apiCall<EngineStatus>("GET", `/api/status/${encodeURIComponent(id)}`);
}

export async function stopEngine(id: string): Promise<{ message: string }> {
  if (!id || id.length > 100) throw new Error("ID de sessão inválido");
  return apiCall<{ message: string }>("POST", `/api/stop/${encodeURIComponent(id)}`);
}
