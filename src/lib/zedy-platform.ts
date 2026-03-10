/**
 * Zedy Checkout Platform — Conhecimento completo para modo API Direto
 * 
 * Arquitetura:
 * - Frontend: Next.js (RSC) em seguro.*.com
 * - Backend: WooCommerce + VendeAgora
 * - API: https://checkout.vendeagora.com/api
 * - Script de integração: checkout.vendeagora.com/scripts/woocommerce.js
 * 
 * Fluxo do Token:
 * token (ex: Z-10YFP03SQV26) → storeId (28515) → checkout.id (44012512)
 * O token resolve para config completa: produto, preço, frete, gateways, branding
 */

// ─── Tipos da Plataforma ───────────────────────────────────────────────

export interface ZedyTokenData {
  token: string;
  storeId: number;
  checkoutId: number;
  product: ZedyProduct;
  store: ZedyStore;
  shipping: ZedyShipping;
  payment: ZedyPayment;
  raw?: Record<string, unknown>;
}

export interface ZedyProduct {
  title: string;
  productId: number;
  shopifyProductId: number;
  variantId: number;
  priceRaw: number;
  quantity: number;
  imageUrl: string;
  isZipcode: boolean;
}

export interface ZedyStore {
  slug: string;
  name: string;
  shopUrl: string;
  apiBase: string;
}

export interface ZedyShipping {
  requiresZipcode: boolean;
  methods: ZedyShippingMethod[];
}

export interface ZedyShippingMethod {
  id: string;
  name: string;
  price: number;
  deadline: string;
}

export interface ZedyPayment {
  gateways: string[];
  pixDiscount: number;
  installments: ZedyInstallment[];
}

export interface ZedyInstallment {
  number: number;
  value: number;
  total: number;
}

// ─── Dados do Pedido (para submissão direta) ───────────────────────────

export interface ZedyOrderData {
  name: string;
  email: string;
  phone: string;
  cpf: string;
  zipcode: string;
  address: string;
  number: string;
  complement?: string;
  neighborhood: string;
  city: string;
  state: string;
  shippingMethodId: string;
  paymentMethod: "pix" | "credit_card" | "boleto";
}

export interface ZedyDirectPayload {
  token: string;
  storeId: number;
  checkoutId: number;
  order: ZedyOrderData;
}

// ─── Constantes da Plataforma ──────────────────────────────────────────

export const ZEDY_CONSTANTS = {
  /** API base da VendeAgora/Zedy */
  API_BASE: "https://checkout.vendeagora.com/api",
  
  /** Script de integração WooCommerce → Zedy */
  WOOCOMMERCE_SCRIPT: "https://checkout.vendeagora.com/scripts/woocommerce.js",
  
  /** Padrão de URL de checkout Zedy */
  CHECKOUT_URL_PATTERN: /^https?:\/\/seguro\.[^/]+\/checkout\/([A-Z0-9-]+)\/?$/i,
  
  /** Padrão de token Zedy */
  TOKEN_PATTERN: /^Z-[A-Z0-9]+$/i,
  
  /** Headers padrão para Server Actions (Next.js RSC) */
  RSC_HEADERS: {
    "accept": "text/x-component",
    "content-type": "text/plain;charset=UTF-8",
    "next-action": "", // preenchido dinamicamente
    "next-router-state-tree": "", // preenchido dinamicamente
  },
  
  /** Lojas conhecidas (cache de resolução) */
  KNOWN_STORES: {
    "texano-2602": {
      slug: "texano-2602",
      name: "Texano Store",
      shopUrl: "https://texanostoreoficial.com",
      apiBase: "https://checkout.vendeagora.com/api",
    },
  } as Record<string, ZedyStore>,
} as const;

// ─── Utilidades ────────────────────────────────────────────────────────

/**
 * Extrai o token Zedy de uma URL de checkout
 */
export function extractTokenFromUrl(url: string): string | null {
  const match = url.match(ZEDY_CONSTANTS.CHECKOUT_URL_PATTERN);
  return match ? match[1] : null;
}

/**
 * Valida se uma string é um token Zedy válido
 */
export function isValidZedyToken(token: string): boolean {
  return ZEDY_CONSTANTS.TOKEN_PATTERN.test(token);
}

/**
 * Detecta se a URL é de um checkout Zedy
 */
export function isZedyCheckoutUrl(url: string): boolean {
  return ZEDY_CONSTANTS.CHECKOUT_URL_PATTERN.test(url);
}

/**
 * Detecta a plataforma a partir de uma URL
 */
export function detectPlatform(url: string): "zedy" | "yampi" | "unknown" {
  if (url.includes("vendeagora.com") || url.match(/seguro\.[^/]+\/checkout\/Z-/i)) {
    return "zedy";
  }
  if (url.includes("yampi.com") || url.includes("checkout.yampi")) {
    return "yampi";
  }
  return "unknown";
}

/**
 * Gera dados aleatórios para um pedido (mesma lógica do motor)
 */
export function generateRandomOrderData(cpf?: string): Omit<ZedyOrderData, "zipcode" | "address" | "number" | "neighborhood" | "city" | "state" | "shippingMethodId" | "paymentMethod"> {
  const firstNames = [
    "João", "Maria", "Pedro", "Ana", "Carlos", "Juliana", "Lucas", "Fernanda",
    "Rafael", "Camila", "Bruno", "Amanda", "Diego", "Patricia", "Thiago",
    "Larissa", "Gustavo", "Beatriz", "Rodrigo", "Isabela",
  ];
  const lastNames = [
    "Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves",
    "Pereira", "Lima", "Gomes", "Costa", "Ribeiro", "Martins", "Carvalho",
    "Almeida", "Lopes", "Soares", "Fernandes", "Vieira", "Barbosa",
  ];

  const firstName = firstNames[Math.floor(Math.random() * firstNames.length)];
  const lastName = lastNames[Math.floor(Math.random() * lastNames.length)];
  const name = `${firstName} ${lastName}`;
  
  const emailDomains = ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com.br"];
  const domain = emailDomains[Math.floor(Math.random() * emailDomains.length)];
  const rand = Math.floor(Math.random() * 9999);
  const email = `${firstName.toLowerCase()}${lastName.toLowerCase()}${rand}@${domain}`;
  
  const phone = `67${Math.floor(90000000 + Math.random() * 9999999)}`;

  return {
    name,
    email,
    phone,
    cpf: cpf || generateRandomCpf(),
  };
}

/**
 * Gera um CPF válido aleatório
 */
function generateRandomCpf(): string {
  const rand = (max: number) => Math.floor(Math.random() * max);
  const n = Array.from({ length: 9 }, () => rand(9));
  
  // Primeiro dígito verificador
  let sum = n.reduce((acc, val, i) => acc + val * (10 - i), 0);
  let d1 = 11 - (sum % 11);
  d1 = d1 >= 10 ? 0 : d1;
  n.push(d1);
  
  // Segundo dígito verificador
  sum = n.reduce((acc, val, i) => acc + val * (11 - i), 0);
  let d2 = 11 - (sum % 11);
  d2 = d2 >= 10 ? 0 : d2;
  n.push(d2);
  
  return `${n[0]}${n[1]}${n[2]}.${n[3]}${n[4]}${n[5]}.${n[6]}${n[7]}${n[8]}-${n[9]}${n[10]}`;
}
