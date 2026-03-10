import { useState, useEffect, useRef, useCallback } from "react";
import {
  Play, Square, RefreshCw, Zap, CheckCircle2, XCircle,
  Activity, Clock, AlertTriangle, Loader2, Eye, EyeOff, Monitor, Globe, Wifi
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { MetricCard } from "@/components/MetricCard";
import { FileUploadButton } from "@/components/FileUploadButton";
import { DirectApiPanel } from "@/components/DirectApiPanel";
import { toast } from "sonner";
import {
  startEngine,
  stopEngine,
  getEngineStatus,
  getEngineConfig,
  type StartEnginePayload,
  type EngineStatus,
  type EngineMode,
} from "@/lib/engine-api";

export default function EngineControl() {
  const [targetUrl, setTargetUrl] = useState("https://seguro.texanostoreoficial.com/checkout/Z-07KZD03I0W26/");
  const [proxiesText, setProxiesText] = useState("");
  const [cpfsText, setCpfsText] = useState("");
  const [intervalSec, setIntervalSec] = useState(120);
  const [headless, setHeadless] = useState(true);
  const [rotateAfter, setRotateAfter] = useState(1);
  const [isProductUrl, setIsProductUrl] = useState(false);
  const [captureNetwork, setCaptureNetwork] = useState(false);
  const [engineMode, setEngineMode] = useState<EngineMode>("browser");
  const [directApiConfig, setDirectApiConfig] = useState<StartEnginePayload["direct_api_config"]>(undefined);
  const [sessionId, setSessionId] = useState<string | null>(
    () => localStorage.getItem("phantom_session_id")
  );
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const config = getEngineConfig();
  const isConfigured = !!(config.baseUrl && config.token);

  const pollStatus = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await getEngineStatus(sessionId);
      setStatus(data);
      if (data.status === "stopped" || data.status === "error") {
        stopPolling();
      }
    } catch {
      // silent fail for polling
    }
  }, [sessionId]);

  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    setPolling(true);
    pollRef.current = setInterval(pollStatus, 3000);
    pollStatus();
  }, [pollStatus]);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setPolling(false);
  };

  useEffect(() => {
    if (sessionId) startPolling();
    return () => stopPolling();
  }, [sessionId, startPolling]);

  const handleStart = async () => {
    if (!isConfigured) {
      toast.error("Configure a URL e o Token na página de Configurações primeiro!");
      return;
    }
    if (!targetUrl.trim()) {
      toast.error("Informe a URL do checkout");
      return;
    }

    const proxies = proxiesText
      .split("\n")
      .map((p) => p.trim())
      .filter(Boolean);

    const cpfs = cpfsText
      .split("\n")
      .map((c) => c.trim())
      .filter(Boolean);

    const payload: StartEnginePayload = {
      target_url: targetUrl.trim(),
      proxies,
      interval_seconds: intervalSec,
      headless,
      rotate_after_successes: rotateAfter,
      is_product_url: isProductUrl,
      capture_network: captureNetwork,
      engine_mode: engineMode,
      ...(engineMode === "direct_api" && directApiConfig ? { direct_api_config: directApiConfig } : {}),
      ...(cpfs.length > 0 ? { cpfs } : {}),
    };

    setLoading(true);
    try {
      const result = await startEngine(payload);
      setSessionId(result.id);
      localStorage.setItem("phantom_session_id", result.id);
      toast.success(`Navegador Fantasma iniciado! Sessão: ${result.id}`);
    } catch (err: any) {
      toast.error(err.message || "Erro ao iniciar engine");
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      await stopEngine(sessionId);
      toast.success("Navegador Fantasma parado com sucesso!");
      setSessionId(null);
      localStorage.removeItem("phantom_session_id");
      setStatus(null);
      stopPolling();
    } catch (err: any) {
      toast.error(err.message || "Erro ao parar engine");
    } finally {
      setLoading(false);
    }
  };

  const isRunning = status?.status === "running";
  const uptime = status?.uptime_seconds
    ? `${Math.floor(status.uptime_seconds / 60)}m ${status.uptime_seconds % 60}s`
    : "—";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
          <Monitor className="h-6 w-6 text-primary" /> Navegador Fantasma
        </h1>
        <p className="text-sm text-muted-foreground">
          PHANTOM ENGINE v7.0 — DOM-Intelligence · API Direto · Detecção de Transição
        </p>
      </div>

      {!isConfigured && (
        <Card className="border-chart-warning/30 bg-chart-warning/5">
          <CardContent className="flex items-center gap-3 p-4">
            <AlertTriangle className="h-5 w-5 text-chart-warning shrink-0" />
            <p className="text-sm">
              <strong>Configure primeiro!</strong> Vá em{" "}
              <a href="/settings" className="text-primary underline underline-offset-2">
                Configurações
              </a>{" "}
              e defina a URL base e o Token da API.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Fluxo de Automação */}
      <Card className={`border-primary/20 ${engineMode === "direct_api" ? "bg-chart-warning/5 border-chart-warning/20" : "bg-primary/5"}`}>
        <CardContent className="p-4">
          <p className="text-xs font-semibold text-primary mb-2">
            {engineMode === "direct_api" 
              ? "⚡ MODO API DIRETO — Sem navegador, máxima velocidade" 
              : "🌐 MODO NAVEGADOR — DOM-INTELLIGENCE v7.0"}
          </p>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {engineMode === "direct_api" ? (
              <>
                <span className="rounded bg-chart-warning/10 px-2 py-1 text-chart-warning font-medium">1. Resolve Token</span>
                <span>→</span>
                <span className="rounded bg-chart-warning/10 px-2 py-1 text-chart-warning font-medium">2. Gera Dados</span>
                <span>→</span>
                <span className="rounded bg-chart-warning/10 px-2 py-1 text-chart-warning font-medium">3. POST Pedido</span>
                <span>→</span>
                <span className="rounded bg-chart-warning/10 px-2 py-1 text-chart-warning font-medium">4. Gera PIX ✅</span>
              </>
            ) : (
              <>
                {isProductUrl && (
                  <>
                    <span className="rounded bg-chart-warning/10 px-2 py-1 text-chart-warning font-medium">0. Produto → Carrinho</span>
                    <span>→</span>
                  </>
                )}
                <span className="rounded bg-primary/10 px-2 py-1 text-primary font-medium">🔍 Scan Campos</span>
                <span>→</span>
                <span className="rounded bg-primary/10 px-2 py-1 text-primary font-medium">✏️ Preenche Tudo</span>
                <span>→</span>
                <span className="rounded bg-primary/10 px-2 py-1 text-primary font-medium">🖱️ Clica Botão</span>
                <span>→</span>
                <span className="rounded bg-primary/10 px-2 py-1 text-primary font-medium">🔄 Repete até Sucesso</span>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Status Cards */}
      {status && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            title="Status"
            value={isRunning ? "Rodando" : status.status === "error" ? "Erro" : "Parado"}
            icon={isRunning ? Activity : Square}
            changeType={isRunning ? "positive" : "negative"}
            change={isRunning ? "Navegador ativo" : "Inativo"}
          />
          <MetricCard title="Checkouts Alcançados" value={String(status.successes)} icon={CheckCircle2} changeType="positive" change={`de ${status.total_attempts} sessões`} />
          <MetricCard title="Erros" value={String(status.failures)} icon={XCircle} changeType="negative" change={`de ${status.total_attempts} sessões`} />
          <MetricCard title="Uptime" value={uptime} icon={Clock} />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        {/* Config Form */}
        <Card className="border-border/50">
          <CardHeader>
            <CardTitle className="text-base">Configuração da Sessão Playwright</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>{isProductUrl ? "URL do Produto *" : "URL do Checkout *"}</Label>
                <div className="flex items-center gap-2">
                  <Switch
                    checked={isProductUrl}
                    onCheckedChange={setIsProductUrl}
                    disabled={isRunning}
                  />
                  <Label className="text-xs cursor-pointer text-muted-foreground">
                    {isProductUrl ? "🛒 Link de Produto" : "💳 Link de Checkout"}
                  </Label>
                </div>
              </div>
              <Input
                value={targetUrl}
                onChange={(e) => setTargetUrl(e.target.value)}
                placeholder={isProductUrl
                  ? "https://loja.com/produto/nome-do-produto"
                  : "https://seguro.loja.com/checkout/..."
                }
                disabled={isRunning}
              />
              <p className="text-xs text-muted-foreground">
                {isProductUrl
                  ? "O motor vai abrir o produto, clicar em Comprar, passar pelo carrinho e chegar no checkout automaticamente."
                  : "URL completa da página de checkout alvo."
                }
              </p>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>Proxies (opcional, um por linha)</Label>
                <FileUploadButton
                  label="Carregar proxies.txt"
                  disabled={isRunning}
                  onFileLoaded={(content) => setProxiesText(content.trim())}
                />
              </div>
              <Textarea
                value={proxiesText}
                onChange={(e) => setProxiesText(e.target.value)}
                placeholder={"http://user:pass@proxy1:8080\nsocks5://proxy2:1080\nhttp://user:pass@proxy3:3128"}
                rows={5}
                className="font-mono text-xs"
                disabled={isRunning}
              />
              <p className="text-xs text-muted-foreground">
                Proxies são rotacionados automaticamente. Sem proxy = IP direto do servidor.
                {proxiesText && ` (${proxiesText.split("\n").filter(Boolean).length} carregados)`}
              </p>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>CPFs (opcional, um por linha)</Label>
                <FileUploadButton
                  label="Carregar cpfs.txt"
                  disabled={isRunning}
                  onFileLoaded={(content) => setCpfsText(content.trim())}
                />
              </div>
              <Textarea
                value={cpfsText}
                onChange={(e) => setCpfsText(e.target.value)}
                placeholder={"123.456.789-00\n987.654.321-00"}
                rows={3}
                className="font-mono text-xs"
                disabled={isRunning}
              />
              <p className="text-xs text-muted-foreground">
                Se vazio, o motor usará o arquivo <code className="text-primary">cpfs.txt</code> do servidor.
                {cpfsText && ` (${cpfsText.split("\n").filter(Boolean).length} carregados)`}
              </p>
            </div>

            <div className="flex flex-wrap gap-6 items-end">
              <div className="space-y-2">
                <Label>Intervalo entre sessões (seg)</Label>
                <Input
                  type="number"
                  value={intervalSec}
                  onChange={(e) => setIntervalSec(Number(e.target.value))}
                  className="w-36"
                  min={10}
                  max={3600}
                  disabled={isRunning}
                />
              </div>
              <div className="space-y-2">
                <Label>Girar proxy a cada X sucessos</Label>
                <Input
                  type="number"
                  value={rotateAfter}
                  onChange={(e) => setRotateAfter(Number(e.target.value))}
                  className="w-36"
                  min={1}
                  max={100}
                  disabled={isRunning}
                />
                <p className="text-xs text-muted-foreground">Troca de proxy após N pedidos com sucesso.</p>
              </div>
              <div className="flex items-center gap-3 pb-1">
                <Switch
                  checked={headless}
                  onCheckedChange={setHeadless}
                  disabled={isRunning}
                />
                <div className="flex items-center gap-1.5">
                  {headless ? <EyeOff className="h-4 w-4 text-muted-foreground" /> : <Eye className="h-4 w-4 text-primary" />}
                  <Label className="text-sm cursor-pointer">{headless ? "Invisível" : "Visível"}</Label>
                </div>
              </div>
              <div className="flex items-center gap-3 pb-1">
                <Switch
                  checked={captureNetwork}
                  onCheckedChange={setCaptureNetwork}
                  disabled={isRunning}
                />
                <div className="flex items-center gap-1.5">
                  <Wifi className={`h-4 w-4 ${captureNetwork ? "text-primary" : "text-muted-foreground"}`} />
                  <Label className="text-sm cursor-pointer">{captureNetwork ? "🔍 Captura de Rede" : "Rede OFF"}</Label>
                </div>
              </div>
            </div>

            {/* Dados Gerados Info */}
            <Card className="border-border/30 bg-muted/30">
              <CardContent className="p-3">
                <p className="text-xs font-semibold text-muted-foreground mb-1">DADOS AUTO-GERADOS POR SESSÃO</p>
                <div className="grid grid-cols-2 gap-1 text-xs text-muted-foreground">
                  <span>👤 Nome aleatório (BR)</span>
                  <span>📧 E-mail gerado</span>
                  <span>📱 Celular (67) aleatório</span>
                  <span>🆔 CPF da lista</span>
                </div>
              </CardContent>
            </Card>

            <div className="flex gap-3 pt-2">
              {!isRunning ? (
                <Button onClick={handleStart} disabled={loading || !isConfigured} className="gap-2">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  Iniciar Navegador Fantasma
                </Button>
              ) : (
                <Button variant="destructive" onClick={handleStop} disabled={loading} className="gap-2">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
                  Parar Navegador
                </Button>
              )}
              {sessionId && (
                <Button variant="outline" onClick={pollStatus} disabled={loading} className="gap-2">
                  <RefreshCw className="h-4 w-4" /> Atualizar
                </Button>
              )}
            </div>

            {sessionId && (
              <p className="text-xs text-muted-foreground font-mono">
                Sessão ativa: {sessionId}
              </p>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <DirectApiPanel
            targetUrl={targetUrl}
            engineMode={engineMode}
            onEngineModeChange={setEngineMode}
            onDirectConfigChange={setDirectApiConfig}
            disabled={isRunning}
          />

        <Card className="border-border/50">
          <CardContent className="p-0">
            <Tabs defaultValue="logs" className="w-full">
              <div className="flex items-center justify-between px-4 pt-4 pb-2">
                <TabsList className="h-8">
                  <TabsTrigger value="logs" className="text-xs gap-1.5">
                    <Activity className="h-3.5 w-3.5" /> Logs
                    {polling && <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />}
                  </TabsTrigger>
                  <TabsTrigger value="network" className="text-xs gap-1.5">
                    <Globe className="h-3.5 w-3.5" /> Rede
                    {(status?.captured_requests?.length ?? 0) > 0 && (
                      <span className="text-[10px] bg-primary/20 text-primary px-1.5 rounded-full">
                        {status?.captured_requests?.length}
                      </span>
                    )}
                  </TabsTrigger>
                </TabsList>
              </div>

              <TabsContent value="logs" className="px-4 pb-4 mt-0">
                <div className="h-[440px] overflow-y-auto rounded-md bg-muted/50 p-3 font-mono text-xs space-y-1.5">
                  {!status?.logs?.length && (
                    <p className="text-muted-foreground text-center py-8">
                      Nenhum log ainda. Inicie o navegador fantasma para ver os eventos.
                    </p>
                  )}
                  {status?.logs?.map((log, i) => (
                    <div
                      key={i}
                      className={`flex gap-2 ${
                        log.type === "success"
                          ? "text-primary"
                          : log.type === "error"
                          ? "text-destructive"
                          : "text-muted-foreground"
                      }`}
                    >
                      <span className="text-muted-foreground shrink-0">
                        {new Date(log.timestamp).toLocaleTimeString("pt-BR")}
                      </span>
                      <span>{log.message}</span>
                    </div>
                  ))}
                </div>
              </TabsContent>

              <TabsContent value="network" className="px-4 pb-4 mt-0">
                <div className="h-[440px] overflow-y-auto rounded-md bg-muted/50 p-2 font-mono text-xs space-y-2">
                  {!captureNetwork && (
                    <p className="text-muted-foreground text-center py-8">
                      Ative "Captura de Rede" nas configurações para interceptar as requests do checkout.
                    </p>
                  )}
                  {captureNetwork && !status?.captured_requests?.length && (
                    <p className="text-muted-foreground text-center py-8">
                      Captura ativa. Requests aparecerão aqui durante a automação.
                    </p>
                  )}
                  {status?.captured_requests?.map((req, i) => (
                    <details key={i} className="border border-border/30 rounded-md overflow-hidden">
                      <summary className="cursor-pointer px-3 py-2 hover:bg-muted/80 flex items-center gap-2">
                        <span className={`font-bold ${
                          req.method === "POST" ? "text-chart-warning" :
                          req.method === "GET" ? "text-primary" :
                          "text-destructive"
                        }`}>
                          {req.method}
                        </span>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          req.status >= 200 && req.status < 300 ? "bg-primary/20 text-primary" :
                          req.status >= 400 ? "bg-destructive/20 text-destructive" :
                          "bg-muted text-muted-foreground"
                        }`}>
                          {req.status}
                        </span>
                        <span className="text-muted-foreground truncate">{req.url.substring(0, 70)}</span>
                        <span className="text-muted-foreground/50 ml-auto shrink-0">
                          {new Date(req.timestamp).toLocaleTimeString("pt-BR")}
                        </span>
                      </summary>
                      <div className="px-3 py-2 space-y-2 bg-background/50 border-t border-border/20">
                        <div>
                          <p className="text-muted-foreground font-semibold mb-1">URL completa:</p>
                          <p className="text-primary break-all select-all">{req.url}</p>
                        </div>
                        {Object.keys(req.request_headers || {}).length > 0 && (
                          <div>
                            <p className="text-muted-foreground font-semibold mb-1">Headers:</p>
                            <pre className="bg-muted/50 p-2 rounded text-[10px] overflow-x-auto select-all">
                              {JSON.stringify(req.request_headers, null, 2)}
                            </pre>
                          </div>
                        )}
                        {req.request_body && (
                          <div>
                            <p className="text-chart-warning font-semibold mb-1">Request Body:</p>
                            <pre className="bg-muted/50 p-2 rounded text-[10px] overflow-x-auto max-h-40 select-all">
                              {(() => {
                                try { return JSON.stringify(JSON.parse(req.request_body), null, 2); }
                                catch { return req.request_body; }
                              })()}
                            </pre>
                          </div>
                        )}
                        {req.response_body && (
                          <div>
                            <p className="text-primary font-semibold mb-1">Response Body:</p>
                            <pre className="bg-muted/50 p-2 rounded text-[10px] overflow-x-auto max-h-40 select-all">
                              {(() => {
                                try { return JSON.stringify(JSON.parse(req.response_body), null, 2); }
                                catch { return req.response_body; }
                              })()}
                            </pre>
                          </div>
                        )}
                      </div>
                    </details>
                  ))}
                </div>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
