import { useState } from "react";
import { Plus, Trash2, TestTube2, Save, Wifi, WifiOff } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/StatusBadge";
import { mockApiConfigs, type ApiConfig } from "@/lib/mock-data";
import { toast } from "sonner";

export default function ApiSettings() {
  const [configs, setConfigs] = useState<ApiConfig[]>(mockApiConfigs);
  const [selected, setSelected] = useState<string>(configs[0]?.id || "");

  const current = configs.find((c) => c.id === selected);

  const handleAddConfig = () => {
    const newConfig: ApiConfig = {
      id: `API-${String(configs.length + 1).padStart(3, "0")}`,
      name: `Nova API ${configs.length + 1}`,
      baseUrl: "",
      headers: [{ key: "Content-Type", value: "application/json" }],
      token: "",
      status: "disconnected",
      lastTest: null,
    };
    setConfigs((prev) => [...prev, newConfig]);
    setSelected(newConfig.id);
    toast.success("Nova configuração criada");
  };

  const updateCurrent = (updates: Partial<ApiConfig>) => {
    setConfigs((prev) => prev.map((c) => c.id === selected ? { ...c, ...updates } : c));
  };

  const handleAddHeader = () => {
    if (!current) return;
    updateCurrent({ headers: [...current.headers, { key: "", value: "" }] });
  };

  const handleUpdateHeader = (index: number, field: "key" | "value", val: string) => {
    if (!current) return;
    const headers = [...current.headers];
    headers[index] = { ...headers[index], [field]: val };
    updateCurrent({ headers });
  };

  const handleRemoveHeader = (index: number) => {
    if (!current) return;
    updateCurrent({ headers: current.headers.filter((_, i) => i !== index) });
  };

  const handleTest = () => {
    if (!current?.baseUrl) {
      toast.error("Informe a URL base da API");
      return;
    }
    toast.loading("Testando conexão...");
    setTimeout(() => {
      toast.dismiss();
      const success = Math.random() > 0.3;
      updateCurrent({
        status: success ? "connected" : "error",
        lastTest: new Date().toISOString(),
      });
      if (success) toast.success("Conexão estabelecida com sucesso!");
      else toast.error("Falha na conexão. Verifique as configurações.");
    }, 1500);
  };

  const handleSave = () => {
    toast.success("Configurações salvas no localStorage!");
    localStorage.setItem("api_configs", JSON.stringify(configs));
  };

  const handleDelete = (id: string) => {
    setConfigs((prev) => prev.filter((c) => c.id !== id));
    if (selected === id) setSelected(configs[0]?.id || "");
    toast.success("Configuração removida");
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Configurações de API</h1>
          <p className="text-sm text-muted-foreground">Configure seus gateways de pagamento</p>
        </div>
        <Button onClick={handleAddConfig}><Plus className="mr-2 h-4 w-4" /> Nova API</Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <Card className="border-border/50">
          <CardContent className="p-2">
            <div className="space-y-1">
              {configs.map((config) => (
                <button
                  key={config.id}
                  onClick={() => setSelected(config.id)}
                  className={`w-full flex items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors ${
                    selected === config.id ? "bg-primary/10 text-primary" : "hover:bg-muted"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {config.status === "connected" ? <Wifi className="h-3.5 w-3.5 text-primary" /> : <WifiOff className="h-3.5 w-3.5 text-muted-foreground" />}
                    <span className="font-medium">{config.name}</span>
                  </div>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {current && (
          <Card className="border-border/50">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">{current.name}</CardTitle>
              <div className="flex items-center gap-2">
                <StatusBadge status={current.status} />
                <Button variant="ghost" size="icon" onClick={() => handleDelete(current.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-2">
                <Label>Nome da Configuração</Label>
                <Input value={current.name} onChange={(e) => updateCurrent({ name: e.target.value })} />
              </div>
              <div className="space-y-2">
                <Label>URL Base da API</Label>
                <Input value={current.baseUrl} onChange={(e) => updateCurrent({ baseUrl: e.target.value })} placeholder="https://api.gateway.com/v1" />
              </div>
              <div className="space-y-2">
                <Label>Token de Autenticação</Label>
                <Input type="password" value={current.token} onChange={(e) => updateCurrent({ token: e.target.value })} placeholder="sk_live_..." />
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label>Headers Customizados</Label>
                  <Button variant="outline" size="sm" onClick={handleAddHeader}><Plus className="mr-1 h-3 w-3" /> Header</Button>
                </div>
                {current.headers.map((header, i) => (
                  <div key={i} className="flex gap-2">
                    <Input value={header.key} onChange={(e) => handleUpdateHeader(i, "key", e.target.value)} placeholder="Chave" className="flex-1" />
                    <Input value={header.value} onChange={(e) => handleUpdateHeader(i, "value", e.target.value)} placeholder="Valor" className="flex-1" />
                    <Button variant="ghost" size="icon" onClick={() => handleRemoveHeader(i)}><Trash2 className="h-3.5 w-3.5 text-destructive" /></Button>
                  </div>
                ))}
              </div>

              {current.lastTest && (
                <p className="text-xs text-muted-foreground">Último teste: {new Date(current.lastTest).toLocaleString("pt-BR")}</p>
              )}

              <div className="flex gap-2 pt-2">
                <Button variant="outline" onClick={handleTest}><TestTube2 className="mr-2 h-4 w-4" /> Testar Conexão</Button>
                <Button onClick={handleSave}><Save className="mr-2 h-4 w-4" /> Salvar</Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
