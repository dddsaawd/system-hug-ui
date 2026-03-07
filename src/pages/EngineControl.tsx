import { useState, useEffect, useRef, useCallback } from "react";
import {
  Play, Square, RefreshCw, Zap, CheckCircle2, XCircle,
  Activity, Clock, AlertTriangle, Loader2
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { MetricCard } from "@/components/MetricCard";
import { toast } from "sonner";
import {
  startEngine,
  stopEngine,
  getEngineStatus,
  getEngineConfig,
  type StartEnginePayload,
  type EngineStatus,
} from "@/lib/engine-api";

export default function EngineControl() {
  const [targetUrl, setTargetUrl] = useState("");
  const [proxiesText, setProxiesText] = useState("");
  const [cpfsText, setCpfsText] = useState("");
  const [intervalSec, setIntervalSec] = useState(120);
  const [maxRetries, setMaxRetries] = useState(5);

  const [sessionId, setSessionId] = useState<string | null>(
    () => localStorage.getItem("phantom_session_id")
  );
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const config = getEngineConfig();
  const isConfigured = !!(config.baseUrl && config.token);

  // Poll status
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

    if (proxies.length === 0) {
      toast.error("Adicione pelo menos 1 proxy");
      return;
    }

    const cpfs = cpfsText
      .split("\n")
      .map((c) => c.trim())
      .filter(Boolean);

    const payload: StartEnginePayload = {
      target_url: targetUrl.trim(),
      proxies,
      interval_seconds: intervalSec,
      max_retries: maxRetries,
      ...(cpfs.length > 0 ? { cpfs } : {}),
    };

    setLoading(true);
    try {
      const result = await startEngine(payload);
      setSessionId(result.id);
      localStorage.setItem("phantom_session_id", result.id);
      toast.success(`Engine iniciada! Sessão: ${result.id}`);
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
      toast.success("Engine parada com sucesso!");
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
          <Zap className="h-6 w-6 text-primary" /> Motor de Execução
        </h1>
        <p className="text-sm text-muted-foreground">
          Controle do PHANTOM ENGINE — Iniciar, monitorar e parar sessões
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

      {/* Status Cards */}
      {status && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            title="Status"
            value={isRunning ? "Rodando" : status.status === "error" ? "Erro" : "Parado"}
            icon={isRunning ? Activity : Square}
            changeType={isRunning ? "positive" : "negative"}
            change={isRunning ? "Ativo agora" : "Inativo"}
          />
          <MetricCard title="Sucessos" value={String(status.successes)} icon={CheckCircle2} changeType="positive" change={`de ${status.total_attempts} tentativas`} />
          <MetricCard title="Falhas" value={String(status.failures)} icon={XCircle} changeType="negative" change={`de ${status.total_attempts} tentativas`} />
          <MetricCard title="Uptime" value={uptime} icon={Clock} />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        {/* Config Form */}
        <Card className="border-border/50">
          <CardHeader>
            <CardTitle className="text-base">Configuração da Sessão</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>URL do Checkout *</Label>
              <Input
                value={targetUrl}
                onChange={(e) => setTargetUrl(e.target.value)}
                placeholder="https://checkout.exemplo.com/produto"
                disabled={isRunning}
              />
            </div>

            <div className="space-y-2">
              <Label>Proxies * (um por linha)</Label>
              <Textarea
                value={proxiesText}
                onChange={(e) => setProxiesText(e.target.value)}
                placeholder={"http://user:pass@proxy1:8080\nhttp://user:pass@proxy2:8080\nsocks5://proxy3:1080"}
                rows={5}
                className="font-mono text-xs"
                disabled={isRunning}
              />
            </div>

            <div className="space-y-2">
              <Label>CPFs (opcional, um por linha)</Label>
              <Textarea
                value={cpfsText}
                onChange={(e) => setCpfsText(e.target.value)}
                placeholder={"123.456.789-00\n987.654.321-00"}
                rows={3}
                className="font-mono text-xs"
                disabled={isRunning}
              />
              <p className="text-xs text-muted-foreground">Se vazio, o motor usará o arquivo cpfs.txt do servidor.</p>
            </div>

            <div className="flex flex-wrap gap-4">
              <div className="space-y-2">
                <Label>Intervalo (segundos)</Label>
                <Input
                  type="number"
                  value={intervalSec}
                  onChange={(e) => setIntervalSec(Number(e.target.value))}
                  className="w-36"
                  min={1}
                  max={3600}
                  disabled={isRunning}
                />
              </div>
              <div className="space-y-2">
                <Label>Máx. Retentativas</Label>
                <Input
                  type="number"
                  value={maxRetries}
                  onChange={(e) => setMaxRetries(Number(e.target.value))}
                  className="w-36"
                  min={1}
                  max={100}
                  disabled={isRunning}
                />
              </div>
            </div>

            <div className="flex gap-3 pt-2">
              {!isRunning ? (
                <Button onClick={handleStart} disabled={loading || !isConfigured} className="gap-2">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  Iniciar Engine
                </Button>
              ) : (
                <Button variant="destructive" onClick={handleStop} disabled={loading} className="gap-2">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
                  Parar Engine
                </Button>
              )}
              {sessionId && (
                <Button variant="outline" onClick={pollStatus} disabled={loading} className="gap-2">
                  <RefreshCw className="h-4 w-4" /> Atualizar Status
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

        {/* Live Logs */}
        <Card className="border-border/50">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Activity className="h-4 w-4" /> Logs em Tempo Real
              {polling && <span className="h-2 w-2 rounded-full bg-primary animate-pulse" />}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[400px] overflow-y-auto rounded-md bg-muted/50 p-3 font-mono text-xs space-y-1.5">
              {!status?.logs?.length && (
                <p className="text-muted-foreground text-center py-8">
                  Nenhum log ainda. Inicie a engine para ver os eventos.
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
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
