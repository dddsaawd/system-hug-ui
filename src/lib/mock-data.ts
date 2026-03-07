export interface Transaction {
  id: string;
  customer: string;
  email: string;
  amount: number;
  status: "approved" | "declined" | "pending" | "refunded";
  date: string;
  method: string;
  retries: number;
}

export interface CheckoutLink {
  id: string;
  name: string;
  product: string;
  amount: number;
  url: string;
  apiUrl: string;
  status: "active" | "inactive";
  created: string;
  clicks: number;
  conversions: number;
}

export interface ApiConfig {
  id: string;
  name: string;
  baseUrl: string;
  headers: { key: string; value: string }[];
  token: string;
  status: "connected" | "disconnected" | "error";
  lastTest: string | null;
}

export interface RetryRule {
  id: string;
  transactionId: string;
  maxRetries: number;
  interval: number; // seconds
  currentRetry: number;
  status: "pending" | "success" | "failed" | "exhausted";
}

export const mockTransactions: Transaction[] = [
  { id: "TXN-001", customer: "João Silva", email: "joao@email.com", amount: 297.00, status: "approved", date: "2026-03-07T14:30:00", method: "Cartão de Crédito", retries: 0 },
  { id: "TXN-002", customer: "Maria Santos", email: "maria@email.com", amount: 497.00, status: "approved", date: "2026-03-07T13:15:00", method: "PIX", retries: 0 },
  { id: "TXN-003", customer: "Pedro Costa", email: "pedro@email.com", amount: 197.00, status: "declined", date: "2026-03-07T12:45:00", method: "Cartão de Crédito", retries: 2 },
  { id: "TXN-004", customer: "Ana Oliveira", email: "ana@email.com", amount: 997.00, status: "pending", date: "2026-03-07T11:30:00", method: "Boleto", retries: 0 },
  { id: "TXN-005", customer: "Lucas Lima", email: "lucas@email.com", amount: 147.00, status: "approved", date: "2026-03-07T10:00:00", method: "Cartão de Crédito", retries: 1 },
  { id: "TXN-006", customer: "Fernanda Alves", email: "fer@email.com", amount: 597.00, status: "declined", date: "2026-03-06T22:30:00", method: "Cartão de Crédito", retries: 3 },
  { id: "TXN-007", customer: "Ricardo Mendes", email: "ricardo@email.com", amount: 397.00, status: "approved", date: "2026-03-06T20:15:00", method: "PIX", retries: 0 },
  { id: "TXN-008", customer: "Camila Rocha", email: "camila@email.com", amount: 797.00, status: "refunded", date: "2026-03-06T18:45:00", method: "Cartão de Crédito", retries: 0 },
  { id: "TXN-009", customer: "Bruno Ferreira", email: "bruno@email.com", amount: 247.00, status: "approved", date: "2026-03-06T16:00:00", method: "PIX", retries: 0 },
  { id: "TXN-010", customer: "Juliana Dias", email: "juliana@email.com", amount: 347.00, status: "declined", date: "2026-03-06T14:30:00", method: "Cartão de Crédito", retries: 1 },
];

export const mockCheckoutLinks: CheckoutLink[] = [
  { id: "LNK-001", name: "Curso Completo", product: "Curso de Marketing Digital", amount: 497.00, url: "https://pay.example.com/curso-mkt", apiUrl: "https://api.gateway.com/v1/charge", status: "active", created: "2026-03-01", clicks: 1240, conversions: 186 },
  { id: "LNK-002", name: "E-book Premium", product: "E-book Vendas Online", amount: 97.00, url: "https://pay.example.com/ebook-vendas", apiUrl: "https://api.gateway.com/v1/charge", status: "active", created: "2026-02-15", clicks: 890, conversions: 134 },
  { id: "LNK-003", name: "Mentoria VIP", product: "Mentoria Individual", amount: 1997.00, url: "https://pay.example.com/mentoria", apiUrl: "https://api.gateway.com/v1/charge", status: "inactive", created: "2026-02-10", clicks: 450, conversions: 23 },
];

export const mockApiConfigs: ApiConfig[] = [
  { id: "API-001", name: "Gateway Principal", baseUrl: "https://api.gateway.com/v1", headers: [{ key: "Content-Type", value: "application/json" }], token: "sk_live_***********", status: "connected", lastTest: "2026-03-07T10:00:00" },
  { id: "API-002", name: "Gateway Backup", baseUrl: "https://api.backup-gw.com/v2", headers: [{ key: "Content-Type", value: "application/json" }, { key: "X-Merchant-Id", value: "MRC-123" }], token: "pk_test_***********", status: "disconnected", lastTest: null },
];

export const chartData7days = [
  { day: "Seg", approved: 12, declined: 3, revenue: 4250 },
  { day: "Ter", approved: 18, declined: 2, revenue: 6430 },
  { day: "Qua", approved: 15, declined: 5, revenue: 5120 },
  { day: "Qui", approved: 22, declined: 4, revenue: 8790 },
  { day: "Sex", approved: 28, declined: 3, revenue: 11200 },
  { day: "Sáb", approved: 20, declined: 6, revenue: 7680 },
  { day: "Dom", approved: 14, declined: 2, revenue: 5340 },
];
