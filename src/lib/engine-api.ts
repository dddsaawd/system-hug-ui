import { z } from "zod";
import type { ZedyDirectPayload, ZedyTokenData, ZedyProduct, ZedyStore, ZedyPayment, ZedyShipping } from "./zedy-platform";
import { extractTokenFromUrl, isValidZedyToken, ZEDY_CONSTANTS } from "./zedy-platform";

// ─── Engine Mode ───────────────────────────────────────────────────────
export type EngineMode = "browser" | "direct_api";

// Validation schemas
export const startEngineSchema = z.object({
  target_url: z.string().trim().url({ message: "URL inválida" }).max(2048, { message: "URL muito longa" }),
  proxies: z.array(z.string().trim().min(1)).default([]),
  interval_seconds: z.number().min(1).max(3600).default(120),
  cpfs: z.array(z.string().trim()).optional(),
  headless: z.boolean().default(true),
  rotate_after_successes: z.number().min(1).max(100).default(1),
  is_product_url: z.boolean().default(false),
  capture_network: z.boolean().default(false),
  engine_mode: z.enum(["browser", "direct_api"]).default("browser"),
  direct_api_config: z.object({
    platform: z.enum(["zedy", "yampi"]),
    token: z.string().min(1),
    store_id: z.number().optional(),
    checkout_id: z.number().optional(),
    payment_method: z.enum(["pix", "credit_card", "boleto"]).default("pix"),
    zipcode: z.string().optional(),
  }).optional(),
});

export type StartEnginePayload = z.infer<typeof startEngineSchema>;

export interface CapturedRequest {
  timestamp: string;
  method: string;
  url: string;
  status: number;
  request_headers: Record<string, string>;
  request_body: string | null;
  response_body: string | null;
  content_type: string;
}

export interface EngineStatus {
  id: string;
  status: "running" | "stopped" | "error";
  successes: number;
  failures: number;
  total_attempts: number;
  uptime_seconds: number;
  logs: { timestamp: string; message: string; type: "success" | "error" | "info" }[];
  captured_requests: CapturedRequest[];
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

// ─── Zedy Token Resolution ─────────────────────────────────────────────

export interface ZedyResolvedToken {
  token: string;
  storeId: number;
  checkoutId: number;
  product: {
    title: string;
    productId: number;
    variantId: number;
    price: number;
    quantity: number;
    imageUrl: string;
  };
  store: {
    name: string;
    slug: string;
  };
  payment: {
    gateways: string[];
    pixDiscount: number;
  };
  shipping: {
    requiresZipcode: boolean;
  };
}

/**
 * Resolve um token Zedy via backend proxy.
 * O backend faz GET na página do checkout, extrai o JSON hidratado do RSC
 * e retorna storeId, checkoutId, produto, gateways e config.
 * 
 * Endpoint backend: POST /api/zedy/resolve-token
 */
export async function resolveZedyToken(tokenOrUrl: string): Promise<ZedyResolvedToken> {
  // Aceita tanto token puro quanto URL completa
  let token = tokenOrUrl;
  if (tokenOrUrl.startsWith("http")) {
    const extracted = extractTokenFromUrl(tokenOrUrl);
    if (!extracted) throw new Error("URL não contém um token Zedy válido");
    token = extracted;
  }
  
  if (!isValidZedyToken(token)) {
    throw new Error(`Token Zedy inválido: ${token}`);
  }

  return apiCall<ZedyResolvedToken>("POST", "/api/zedy/resolve-token", { token });
}

/**
 * Resolve token localmente parseando o HTML do checkout (fallback client-side).
 * Usa um proxy CORS ou funciona se o backend não tiver o endpoint implementado.
 * 
 * Extrai dados do __NEXT_DATA__ ou do payload RSC hidratado no HTML.
 */
export function parseZedyHtmlPayload(html: string): ZedyResolvedToken | null {
  try {
    // Tenta extrair __NEXT_DATA__ (SSR padrão Next.js)
    const nextDataMatch = html.match(/<script[^>]*id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
    if (nextDataMatch) {
      const data = JSON.parse(nextDataMatch[1]);
      const props = data?.props?.pageProps;
      if (props?.checkout) {
        return extractFromCheckoutProps(props);
      }
    }

    // Tenta extrair do payload RSC hidratado inline (self.__next_f.push)
    const rscChunks: string[] = [];
    const rscPattern = /self\.__next_f\.push\(\[[\d,]*"([^"]*(?:\\.[^"]*)*)"\]\)/g;
    let match: RegExpExecArray | null;
    while ((match = rscPattern.exec(html)) !== null) {
      // Unescape o conteúdo
      const chunk = match[1]
        .replace(/\\n/g, "\n")
        .replace(/\\"/g, '"')
        .replace(/\\\\/g, "\\");
      rscChunks.push(chunk);
    }

    // Procura por JSON objects dentro dos chunks RSC
    const fullPayload = rscChunks.join("");
    
    // Busca padrões conhecidos: "token":"Z-...", "storeId":..., "checkout":{"id":...}
    const tokenMatch = fullPayload.match(/"token"\s*:\s*"(Z-[A-Z0-9]+)"/i);
    const storeIdMatch = fullPayload.match(/"storeId"\s*:\s*(\d+)/);
    const checkoutIdMatch = fullPayload.match(/"checkout"\s*:\s*\{[^}]*"id"\s*:\s*(\d+)/);
    
    // Produto
    const titleMatch = fullPayload.match(/"title"\s*:\s*"([^"]+)"/);
    const productIdMatch = fullPayload.match(/"productId"\s*:\s*(\d+)/);
    const variantIdMatch = fullPayload.match(/"variantId"\s*:\s*(\d+)/) 
      || fullPayload.match(/"shopifyProductId"\s*:\s*(\d+)/);
    const priceMatch = fullPayload.match(/"priceRaw"\s*:\s*([\d.]+)/)
      || fullPayload.match(/"price"\s*:\s*([\d.]+)/);
    const imageMatch = fullPayload.match(/"image"\s*:\s*"(https?:\/\/[^"]+)"/);
    const quantityMatch = fullPayload.match(/"quantity"\s*:\s*(\d+)/);
    const isZipcodeMatch = fullPayload.match(/"isZipcode"\s*:\s*(true|false)/);

    // Store
    const storeNameMatch = fullPayload.match(/"storeName"\s*:\s*"([^"]+)"/)
      || fullPayload.match(/"name"\s*:\s*"([^"]+)"/);
    const storeSlugMatch = fullPayload.match(/"slug"\s*:\s*"([^"]+)"/);

    // PIX discount
    const pixDiscountMatch = fullPayload.match(/"pixDiscount"\s*:\s*([\d.]+)/)
      || fullPayload.match(/"pix_discount"\s*:\s*([\d.]+)/);

    // Gateways
    const gatewayMatches = fullPayload.match(/"gateway[s]?"\s*:\s*\[([^\]]*)\]/);
    let gateways: string[] = [];
    if (gatewayMatches) {
      gateways = gatewayMatches[1]
        .match(/"([^"]+)"/g)
        ?.map(g => g.replace(/"/g, "")) || [];
    }

    if (!tokenMatch && !storeIdMatch && !checkoutIdMatch) {
      return null;
    }

    return {
      token: tokenMatch?.[1] || "",
      storeId: storeIdMatch ? parseInt(storeIdMatch[1]) : 0,
      checkoutId: checkoutIdMatch ? parseInt(checkoutIdMatch[1]) : 0,
      product: {
        title: titleMatch?.[1] || "Produto desconhecido",
        productId: productIdMatch ? parseInt(productIdMatch[1]) : 0,
        variantId: variantIdMatch ? parseInt(variantIdMatch[1]) : 0,
        price: priceMatch ? parseFloat(priceMatch[1]) : 0,
        quantity: quantityMatch ? parseInt(quantityMatch[1]) : 1,
        imageUrl: imageMatch?.[1] || "",
      },
      store: {
        name: storeNameMatch?.[1] || "",
        slug: storeSlugMatch?.[1] || "",
      },
      payment: {
        gateways,
        pixDiscount: pixDiscountMatch ? parseFloat(pixDiscountMatch[1]) : 0,
      },
      shipping: {
        requiresZipcode: isZipcodeMatch?.[1] === "true",
      },
    };
  } catch (err) {
    console.error("[Zedy Parser] Erro ao parsear HTML:", err);
    return null;
  }
}

/**
 * Helper para extrair dados do pageProps (quando __NEXT_DATA__ está disponível)
 */
function extractFromCheckoutProps(props: Record<string, unknown>): ZedyResolvedToken {
  const checkout = props.checkout as Record<string, unknown> || {};
  const product = (checkout.products as Record<string, unknown>[])?.[0] || {} as Record<string, unknown>;
  const store = props.store as Record<string, unknown> || {};
  const payment = props.payment as Record<string, unknown> || {};

  return {
    token: (props.token as string) || (checkout.token as string) || "",
    storeId: (checkout.storeId as number) || (props.storeId as number) || 0,
    checkoutId: (checkout.id as number) || 0,
    product: {
      title: (product.title as string) || "",
      productId: (product.productId as number) || 0,
      variantId: (product.variantId as number) || (product.shopifyProductId as number) || 0,
      price: (product.priceRaw as number) || (product.price as number) || 0,
      quantity: (product.quantity as number) || 1,
      imageUrl: (product.image as string) || "",
    },
    store: {
      name: (store.name as string) || "",
      slug: (store.slug as string) || "",
    },
    payment: {
      gateways: (payment.gateways as string[]) || [],
      pixDiscount: (payment.pixDiscount as number) || 0,
    },
    shipping: {
      requiresZipcode: !!(checkout.isZipcode),
    },
  };
}
