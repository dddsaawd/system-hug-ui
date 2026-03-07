import { useState } from "react";
import { RotateCcw, Play, Settings2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/StatusBadge";
import { mockTransactions } from "@/lib/mock-data";
import { toast } from "sonner";

interface RetryLog {
  attempt: number;
  date: string;
  result: "success" | "failed";
}

export default function Retries() {
  const failedTx = mockTransactions.filter((t) => t.status === "declined");
  const [maxRetries, setMaxRetries] = useState(3);
  const [interval, setInterval_] = useState(30);
  const [retryLogs, setRetryLogs] = useState<Record<string, RetryLog[]>>({});

  const handleRetry = (txId: string) => {
    const success = Math.random() > 0.5;
    const newLog: RetryLog = {
      attempt: (retryLogs[txId]?.length || 0) + 1,
      date: new Date().toISOString(),
      result: success ? "success" : "failed",
    };
    setRetryLogs((prev) => ({
      ...prev,
      [txId]: [...(prev[txId] || []), newLog],
    }));
    if (success) {
      toast.success(`Retentativa ${txId} aprovada!`);
    } else {
      toast.error(`Retentativa ${txId} falhou novamente.`);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Retentativas</h1>
        <p className="text-sm text-muted-foreground">Gerencie cobranças recusadas e configure retentativas</p>
      </div>

      <Card className="border-border/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Settings2 className="h-4 w-4" /> Regras de Retentativa
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-4">
            <div className="space-y-2">
              <Label>Máximo de tentativas</Label>
              <Input type="number" value={maxRetries} onChange={(e) => setMaxRetries(Number(e.target.value))} className="w-32" />
            </div>
            <div className="space-y-2">
              <Label>Intervalo (segundos)</Label>
              <Input type="number" value={interval} onChange={(e) => setInterval_(Number(e.target.value))} className="w-32" />
            </div>
            <div className="flex items-end">
              <Button variant="secondary" onClick={() => toast.success("Regras salvas!")}>Salvar Regras</Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/50">
        <CardHeader>
          <CardTitle className="text-base">Transações Recusadas ({failedTx.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead>Valor</TableHead>
                <TableHead>Tentativas</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Ação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {failedTx.map((tx) => {
                const logs = retryLogs[tx.id] || [];
                const lastLog = logs[logs.length - 1];
                const totalRetries = tx.retries + logs.length;
                const isExhausted = totalRetries >= maxRetries;
                const isSuccess = lastLog?.result === "success";

                return (
                  <TableRow key={tx.id}>
                    <TableCell className="font-mono text-xs">{tx.id}</TableCell>
                    <TableCell>
                      <p className="text-sm font-medium">{tx.customer}</p>
                      <p className="text-xs text-muted-foreground">{tx.email}</p>
                    </TableCell>
                    <TableCell className="font-mono font-medium">R$ {tx.amount.toLocaleString("pt-BR")}</TableCell>
                    <TableCell className="font-mono text-sm">{totalRetries}/{maxRetries}</TableCell>
                    <TableCell>
                      <StatusBadge status={isSuccess ? "success" : isExhausted ? "exhausted" : "failed"} />
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={isExhausted || isSuccess}
                        onClick={() => handleRetry(tx.id)}
                      >
                        <Play className="mr-1 h-3 w-3" /> Retentar
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {Object.entries(retryLogs).length > 0 && (
        <Card className="border-border/50">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <RotateCcw className="h-4 w-4" /> Log de Retentativas
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Transação</TableHead>
                  <TableHead>Tentativa</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead>Resultado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(retryLogs).flatMap(([txId, logs]) =>
                  logs.map((log, i) => (
                    <TableRow key={`${txId}-${i}`}>
                      <TableCell className="font-mono text-xs">{txId}</TableCell>
                      <TableCell>#{log.attempt}</TableCell>
                      <TableCell className="text-xs">{new Date(log.date).toLocaleString("pt-BR")}</TableCell>
                      <TableCell><StatusBadge status={log.result} /></TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
