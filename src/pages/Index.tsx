import { DollarSign, TrendingUp, CheckCircle2, XCircle } from "lucide-react";
import { MetricCard } from "@/components/MetricCard";
import { StatusBadge } from "@/components/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Bar, BarChart, XAxis, YAxis, CartesianGrid } from "recharts";
import { mockTransactions, chartData7days } from "@/lib/mock-data";

const chartConfig = {
  approved: { label: "Aprovadas", color: "hsl(var(--primary))" },
  declined: { label: "Recusadas", color: "hsl(var(--destructive))" },
};

export default function Index() {
  const totalRevenue = mockTransactions
    .filter((t) => t.status === "approved")
    .reduce((sum, t) => sum + t.amount, 0);
  const approvedCount = mockTransactions.filter((t) => t.status === "approved").length;
  const declinedCount = mockTransactions.filter((t) => t.status === "declined").length;
  const conversionRate = ((approvedCount / mockTransactions.length) * 100).toFixed(1);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Visão geral do seu gateway de pagamentos</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard title="Receita Total" value={`R$ ${totalRevenue.toLocaleString("pt-BR")}`} change="+12.5% vs ontem" changeType="positive" icon={DollarSign} />
        <MetricCard title="Taxa de Conversão" value={`${conversionRate}%`} change="+2.1% vs ontem" changeType="positive" icon={TrendingUp} />
        <MetricCard title="Aprovadas" value={String(approvedCount)} change={`de ${mockTransactions.length} transações`} changeType="neutral" icon={CheckCircle2} />
        <MetricCard title="Recusadas" value={String(declinedCount)} change="-3 vs ontem" changeType="positive" icon={XCircle} />
      </div>

      <Card className="border-border/50">
        <CardHeader>
          <CardTitle className="text-base">Transações — Últimos 7 dias</CardTitle>
        </CardHeader>
        <CardContent>
          <ChartContainer config={chartConfig} className="h-[280px] w-full">
            <BarChart data={chartData7days} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="day" tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }} />
              <YAxis tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="approved" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
              <Bar dataKey="declined" fill="hsl(var(--destructive))" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>

      <Card className="border-border/50">
        <CardHeader>
          <CardTitle className="text-base">Últimas Transações</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead>Valor</TableHead>
                <TableHead>Método</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mockTransactions.slice(0, 7).map((tx) => (
                <TableRow key={tx.id}>
                  <TableCell className="font-mono text-xs">{tx.id}</TableCell>
                  <TableCell>
                    <div>
                      <p className="text-sm font-medium">{tx.customer}</p>
                      <p className="text-xs text-muted-foreground">{tx.email}</p>
                    </div>
                  </TableCell>
                  <TableCell className="font-mono font-medium">R$ {tx.amount.toLocaleString("pt-BR")}</TableCell>
                  <TableCell className="text-sm">{tx.method}</TableCell>
                  <TableCell><StatusBadge status={tx.status} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
