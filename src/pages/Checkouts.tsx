import { useState } from "react";
import { Plus, Copy, ExternalLink, Pencil, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/StatusBadge";
import { mockCheckoutLinks, type CheckoutLink } from "@/lib/mock-data";
import { toast } from "sonner";

export default function Checkouts() {
  const [links, setLinks] = useState<CheckoutLink[]>(mockCheckoutLinks);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<CheckoutLink | null>(null);
  const [form, setForm] = useState({ name: "", product: "", amount: "", apiUrl: "" });

  const handleSave = () => {
    if (!form.name || !form.product || !form.amount) {
      toast.error("Preencha todos os campos");
      return;
    }
    if (editing) {
      setLinks((prev) => prev.map((l) => l.id === editing.id ? { ...l, name: form.name, product: form.product, amount: Number(form.amount), apiUrl: form.apiUrl } : l));
      toast.success("Link atualizado!");
    } else {
      const newLink: CheckoutLink = {
        id: `LNK-${String(links.length + 1).padStart(3, "0")}`,
        name: form.name,
        product: form.product,
        amount: Number(form.amount),
        url: `https://pay.example.com/${form.name.toLowerCase().replace(/\s/g, "-")}`,
        apiUrl: form.apiUrl || "https://api.gateway.com/v1/charge",
        status: "active",
        created: new Date().toISOString().split("T")[0],
        clicks: 0,
        conversions: 0,
      };
      setLinks((prev) => [...prev, newLink]);
      toast.success("Link criado com sucesso!");
    }
    setForm({ name: "", product: "", amount: "", apiUrl: "" });
    setEditing(null);
    setOpen(false);
  };

  const handleEdit = (link: CheckoutLink) => {
    setEditing(link);
    setForm({ name: link.name, product: link.product, amount: String(link.amount), apiUrl: link.apiUrl });
    setOpen(true);
  };

  const handleToggle = (id: string) => {
    setLinks((prev) => prev.map((l) => l.id === id ? { ...l, status: l.status === "active" ? "inactive" : "active" } : l));
  };

  const handleCopy = (url: string) => {
    navigator.clipboard.writeText(url);
    toast.success("Link copiado!");
  };

  const handleDelete = (id: string) => {
    setLinks((prev) => prev.filter((l) => l.id !== id));
    toast.success("Link removido!");
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Checkouts</h1>
          <p className="text-sm text-muted-foreground">Gerencie seus links de pagamento</p>
        </div>
        <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditing(null); setForm({ name: "", product: "", amount: "", apiUrl: "" }); } }}>
          <DialogTrigger asChild>
            <Button><Plus className="mr-2 h-4 w-4" /> Novo Link</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{editing ? "Editar Link" : "Criar Novo Link"}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 pt-2">
              <div className="space-y-2">
                <Label>Nome do Link</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ex: Curso Premium" />
              </div>
              <div className="space-y-2">
                <Label>Produto</Label>
                <Input value={form.product} onChange={(e) => setForm({ ...form, product: e.target.value })} placeholder="Ex: Curso de Marketing Digital" />
              </div>
              <div className="space-y-2">
                <Label>Valor (R$)</Label>
                <Input type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} placeholder="497.00" />
              </div>
              <div className="space-y-2">
                <Label>URL da API de Pagamento</Label>
                <Input value={form.apiUrl} onChange={(e) => setForm({ ...form, apiUrl: e.target.value })} placeholder="https://api.gateway.com/v1/charge" />
              </div>
              <Button onClick={handleSave} className="w-full">{editing ? "Salvar Alterações" : "Criar Link"}</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <Card className="border-border/50">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nome</TableHead>
                <TableHead>Produto</TableHead>
                <TableHead>Valor</TableHead>
                <TableHead>Cliques</TableHead>
                <TableHead>Conversões</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {links.map((link) => (
                <TableRow key={link.id}>
                  <TableCell className="font-medium">{link.name}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{link.product}</TableCell>
                  <TableCell className="font-mono font-medium">R$ {link.amount.toLocaleString("pt-BR")}</TableCell>
                  <TableCell>{link.clicks}</TableCell>
                  <TableCell>{link.conversions}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Switch checked={link.status === "active"} onCheckedChange={() => handleToggle(link.id)} />
                      <StatusBadge status={link.status} />
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center justify-end gap-1">
                      <Button variant="ghost" size="icon" onClick={() => handleCopy(link.url)}><Copy className="h-3.5 w-3.5" /></Button>
                      <Button variant="ghost" size="icon" onClick={() => handleEdit(link)}><Pencil className="h-3.5 w-3.5" /></Button>
                      <Button variant="ghost" size="icon" onClick={() => handleDelete(link.id)}><Trash2 className="h-3.5 w-3.5 text-destructive" /></Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
