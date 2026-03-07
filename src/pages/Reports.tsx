import { useState } from "react";
import { Download, Search } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid } from "recharts";
import { StatusBadge } from "@/components/StatusBadge";
import { mockTransactions, chartData7days } from "@/lib/mock-data";
import { toast } from "sonner";

const pieData = [
  { name: "Aprovadas", value: 65, fill: "hsl(var(--primary))" },
  { name: "Recusadas", value: 25, fill: "hsl(var(--destructive))" },
  { name: "Pendentes", value: 10, fill: "hsl(var(--chart-warning))" },
];

const pieConfig = {
  Aprovadas: { label: "Aprovadas", color: "hsl(var(--primary))" },
  Recusadas: { label: "Recusadas", color: "hsl(var(--destructive))" },
  Pendentes: { label: "Pendentes", color: "hsl(var(--chart-warning))" },
};

const revenueConfig = {
  revenue: { label: "Receita", color: "hsl(var(--primary))" },
};

export default function Reports() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const filtered = mockTransactions.filter((tx) => {
    const matchSearch = tx.customer.toLowerCase().includes(search.toLowerCase()) || tx.id.toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === "all" || tx.status === statusFilter;
    return matchSearch && matchStatus;
  });

  const handleExport = () => {
    const csv = ["ID,Cliente,Email,Valor,Status,Método,Data", ...filtered.map((t) => `${t.id},${t.customer},${t.email},${t.amount},${t.status},${t.method},${t.date}`)].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "relatorio-transacoes.csv";
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Relatório exportado!");
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Relatórios</h1>
          <p className="text-sm text-muted-foreground">Análise detalhada das suas transações</p>
        </div>
        <Button variant="outline" onClick={handleExport}><Download className="mr-2 h-4 w-4" /> Exportar CSV</Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="border-border/50">
          <CardHeader>
            <CardTitle className="text-base">Taxa de Aprovação</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer config={pieConfig} className="h-[250px] w-full">
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={60} outerRadius={90} dataKey="value" nameKey="name" label={({ name, value }) => `${name}: ${value}%`}>
                  {pieData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Pie>
                <ChartTooltip content={<ChartTooltipContent />} />
              </PieChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card className="border-border/50">
          <CardHeader>
            <CardTitle className="text-base">Receita por Dia</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer config={revenueConfig} className="h-[250px] w-full">
              <BarChart data={chartData7days}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="day" tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }} />
                <YAxis tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="revenue" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>
      </div>

      <Card className="border-border/50">
        <CardHeader>
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar por cliente ou ID..." className="pl-9" />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[160px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="approved">Aprovados</SelectItem>
                <SelectItem value="declined">Recusados</SelectItem>
                <SelectItem value="pending">Pendentes</SelectItem>
                <SelectItem value="refunded">Reembolsados</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead>Valor</TableHead>
                <TableHead>Método</TableHead>
                <TableHead>Data</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((tx) => (
                <TableRow key={tx.id}>
                  <TableCell className="font-mono text-xs">{tx.id}</TableCell>
                  <TableCell>
                    <p className="text-sm font-medium">{tx.customer}</p>
                    <p className="text-xs text-muted-foreground">{tx.email}</p>
                  </TableCell>
                  <TableCell className="font-mono font-medium">R$ {tx.amount.toLocaleString("pt-BR")}</TableCell>
                  <TableCell className="text-sm">{tx.method}</TableCell>
                  <TableCell className="text-xs">{new Date(tx.date).toLocaleString("pt-BR")}</TableCell>
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
