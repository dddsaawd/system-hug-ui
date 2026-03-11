import { useState } from "react";
import { Zap, Globe, MapPin, CreditCard, ShieldCheck, ArrowRight, Loader2, Copy, Check } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  extractTokenFromUrl,
  isZedyCheckoutUrl,
  detectPlatform,
  generateRandomOrderData,
  ZEDY_CONSTANTS,
  type ZedyTokenData,
} from "@/lib/zedy-platform";
import type { EngineMode } from "@/lib/engine-api";

interface DirectApiPanelProps {
  targetUrl: string;
  engineMode: EngineMode;
  onEngineModeChange: (mode: EngineMode) => void;
  onDirectConfigChange: (config: {
    platform: "zedy" | "yampi";
    token: string;
    store_id?: number;
    checkout_id?: number;
    payment_method: "pix" | "credit_card" | "boleto";
    zipcode?: string;
  }) => void;
  disabled?: boolean;
  cpfsList?: string[];
}

export function DirectApiPanel({
  targetUrl,
  engineMode,
  onEngineModeChange,
  onDirectConfigChange,
  disabled,
  cpfsList = [],
}: DirectApiPanelProps) {
  const [paymentMethod, setPaymentMethod] = useState<"pix" | "credit_card" | "boleto">("pix");
  const [zipcode, setZipcode] = useState("79180000");
  const [storeId, setStoreId] = useState("");
  const [checkoutId, setCheckoutId] = useState("");
  const [copied, setCopied] = useState(false);

  const platform = detectPlatform(targetUrl);
  const isZedy = platform === "zedy";
  const token = extractTokenFromUrl(targetUrl);
  const isDirectReady = isZedy && !!token;

  const previewData = generateRandomOrderData();
  const hasCpfs = cpfsList.length > 0;
  const previewCpf = hasCpfs ? cpfsList[0] : null;

  const handleModeSwitch = (mode: EngineMode) => {
    onEngineModeChange(mode);
    if (mode === "direct_api" && token) {
      onDirectConfigChange({
        platform: "zedy",
        token,
        store_id: storeId ? Number(storeId) : undefined,
        checkout_id: checkoutId ? Number(checkoutId) : undefined,
        payment_method: paymentMethod,
        zipcode: zipcode || undefined,
      });
    }
  };

  const handleConfigUpdate = () => {
    if (!token) return;
    onDirectConfigChange({
      platform: "zedy",
      token,
      store_id: storeId ? Number(storeId) : undefined,
      checkout_id: checkoutId ? Number(checkoutId) : undefined,
      payment_method: paymentMethod,
      zipcode: zipcode || undefined,
    });
  };

  const copyToken = () => {
    if (token) {
      navigator.clipboard.writeText(token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="space-y-4">
      {/* Mode Selector */}
      <div className="flex gap-2">
        <Button
          variant={engineMode === "browser" ? "default" : "outline"}
          size="sm"
          className="gap-2 flex-1"
          onClick={() => handleModeSwitch("browser")}
          disabled={disabled}
        >
          <Globe className="h-4 w-4" />
          Navegador (Browser)
        </Button>
        <Button
          variant={engineMode === "direct_api" ? "default" : "outline"}
          size="sm"
          className="gap-2 flex-1"
          onClick={() => handleModeSwitch("direct_api")}
          disabled={disabled || !isDirectReady}
        >
          <Zap className="h-4 w-4" />
          API Direto
          {isDirectReady && <Badge variant="secondary" className="text-[10px] px-1.5 py-0">PRONTO</Badge>}
        </Button>
      </div>

      {/* Platform Detection */}
      <Card className={`border-border/30 ${isZedy ? "bg-primary/5 border-primary/20" : "bg-muted/30"}`}>
        <CardContent className="p-3 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-muted-foreground">PLATAFORMA DETECTADA</p>
            <Badge variant={isZedy ? "default" : "outline"} className="text-[10px]">
              {isZedy ? "🟢 ZEDY" : platform === "yampi" ? "🟡 YAMPI" : "⚪ DESCONHECIDA"}
            </Badge>
          </div>

          {token && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Token:</span>
                <code className="text-xs text-primary font-bold bg-primary/10 px-2 py-0.5 rounded select-all">
                  {token}
                </code>
                <Button variant="ghost" size="icon" className="h-5 w-5" onClick={copyToken}>
                  {copied ? <Check className="h-3 w-3 text-primary" /> : <Copy className="h-3 w-3" />}
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span>API Base: <code className="text-primary">{ZEDY_CONSTANTS.API_BASE.replace("https://", "")}</code></span>
                <span>Protocolo: <code className="text-primary">RSC (Server Actions)</code></span>
              </div>
            </div>
          )}

          {!isZedy && targetUrl && (
            <p className="text-xs text-muted-foreground">
              ⚠️ Plataforma não suportada para API Direto. Use o modo Navegador.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Direct API Config */}
      {engineMode === "direct_api" && isDirectReady && (
        <Card className="border-primary/20">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2">
              <Zap className="h-4 w-4 text-primary" />
              Configuração API Direto
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Store ID (opcional)</Label>
                <Input
                  value={storeId}
                  onChange={(e) => { setStoreId(e.target.value); }}
                  onBlur={handleConfigUpdate}
                  placeholder="28515"
                  className="h-8 text-xs font-mono"
                  disabled={disabled}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Checkout ID (opcional)</Label>
                <Input
                  value={checkoutId}
                  onChange={(e) => { setCheckoutId(e.target.value); }}
                  onBlur={handleConfigUpdate}
                  placeholder="44012512"
                  className="h-8 text-xs font-mono"
                  disabled={disabled}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Pagamento</Label>
                <Select
                  value={paymentMethod}
                  onValueChange={(v) => {
                    setPaymentMethod(v as typeof paymentMethod);
                    setTimeout(handleConfigUpdate, 0);
                  }}
                  disabled={disabled}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pix">💸 PIX (com desconto)</SelectItem>
                    <SelectItem value="credit_card">💳 Cartão de Crédito</SelectItem>
                    <SelectItem value="boleto">📄 Boleto</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">CEP padrão</Label>
                <Input
                  value={zipcode}
                  onChange={(e) => { setZipcode(e.target.value); }}
                  onBlur={handleConfigUpdate}
                  placeholder="79180-000"
                  className="h-8 text-xs font-mono"
                  maxLength={9}
                  disabled={disabled}
                />
              </div>
            </div>

            {/* Preview dos dados gerados */}
            <Card className="border-border/20 bg-muted/30">
              <CardContent className="p-2.5">
                <p className="text-[10px] font-semibold text-muted-foreground mb-1.5">PREVIEW — DADOS AUTO-GERADOS</p>
                <div className="grid grid-cols-2 gap-1 text-[11px]">
                  <span className="text-muted-foreground">👤 {previewData.name}</span>
                  <span className="text-muted-foreground">📧 {previewData.email}</span>
                  <span className="text-muted-foreground">📱 {previewData.phone}</span>
                  <span className="text-muted-foreground">🆔 {previewData.cpf}</span>
                </div>
              </CardContent>
            </Card>

            {/* Flow Diagram */}
            <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
              <span className="rounded bg-primary/10 px-2 py-1 text-primary font-medium">1. Resolve Token</span>
              <ArrowRight className="h-3 w-3" />
              <span className="rounded bg-primary/10 px-2 py-1 text-primary font-medium">2. Gera Dados</span>
              <ArrowRight className="h-3 w-3" />
              <span className="rounded bg-primary/10 px-2 py-1 text-primary font-medium">3. POST Pedido</span>
              <ArrowRight className="h-3 w-3" />
              <span className="rounded bg-primary/10 px-2 py-1 text-primary font-medium">4. Gera PIX</span>
              <ArrowRight className="h-3 w-3" />
              <ShieldCheck className="h-3.5 w-3.5 text-primary" />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Advantages */}
      {engineMode === "direct_api" && (
        <Card className="border-chart-warning/20 bg-chart-warning/5">
          <CardContent className="p-3">
            <p className="text-[10px] font-semibold text-chart-warning mb-1.5">VANTAGENS DO MODO DIRETO</p>
            <div className="grid grid-cols-2 gap-1 text-[11px] text-muted-foreground">
              <span>⚡ 10x mais rápido (sem browser)</span>
              <span>💾 90% menos RAM/CPU</span>
              <span>🔄 Sessão limpa sempre</span>
              <span>🎯 Nunca falha por DOM</span>
              <span>🌐 Sem problemas de proxy</span>
              <span>📊 100% previsível</span>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
