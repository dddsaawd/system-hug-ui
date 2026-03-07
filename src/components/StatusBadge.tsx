import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const statusConfig: Record<string, { label: string; className: string }> = {
  approved: { label: "Aprovado", className: "bg-primary/15 text-primary border-primary/30" },
  declined: { label: "Recusado", className: "bg-destructive/15 text-destructive border-destructive/30" },
  pending: { label: "Pendente", className: "bg-chart-warning/15 text-chart-warning border-chart-warning/30" },
  refunded: { label: "Reembolsado", className: "bg-chart-info/15 text-chart-info border-chart-info/30" },
  active: { label: "Ativo", className: "bg-primary/15 text-primary border-primary/30" },
  inactive: { label: "Inativo", className: "bg-muted-foreground/15 text-muted-foreground border-muted-foreground/30" },
  connected: { label: "Conectado", className: "bg-primary/15 text-primary border-primary/30" },
  disconnected: { label: "Desconectado", className: "bg-muted-foreground/15 text-muted-foreground border-muted-foreground/30" },
  error: { label: "Erro", className: "bg-destructive/15 text-destructive border-destructive/30" },
  success: { label: "Sucesso", className: "bg-primary/15 text-primary border-primary/30" },
  failed: { label: "Falhou", className: "bg-destructive/15 text-destructive border-destructive/30" },
  exhausted: { label: "Esgotado", className: "bg-chart-warning/15 text-chart-warning border-chart-warning/30" },
};

export function StatusBadge({ status }: { status: string }) {
  const config = statusConfig[status] || { label: status, className: "" };
  return (
    <Badge variant="outline" className={cn("text-[10px] font-semibold uppercase tracking-wider", config.className)}>
      {config.label}
    </Badge>
  );
}
