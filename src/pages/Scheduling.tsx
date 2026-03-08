import { useState } from "react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { CalendarIcon, Clock, Plus, Trash2, CalendarClock, Power } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface ScheduleEntry {
  id: string;
  date: Date;
  startTime: string;
  endTime: string;
  enabled: boolean;
}

export default function Scheduling() {
  const [schedules, setSchedules] = useState<ScheduleEntry[]>(() => {
    const saved = localStorage.getItem("phantom_schedules");
    if (saved) {
      return JSON.parse(saved).map((s: any) => ({ ...s, date: new Date(s.date) }));
    }
    return [];
  });

  const [date, setDate] = useState<Date>();
  const [startTime, setStartTime] = useState("08:00");
  const [endTime, setEndTime] = useState("18:00");

  const saveSchedules = (updated: ScheduleEntry[]) => {
    setSchedules(updated);
    localStorage.setItem("phantom_schedules", JSON.stringify(updated));
  };

  const handleAdd = () => {
    if (!date) {
      toast.error("Selecione uma data");
      return;
    }
    if (!startTime || !endTime) {
      toast.error("Informe o horário de início e fim");
      return;
    }

    const entry: ScheduleEntry = {
      id: crypto.randomUUID(),
      date,
      startTime,
      endTime,
      enabled: true,
    };

    const updated = [...schedules, entry].sort(
      (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
    );
    saveSchedules(updated);
    toast.success("Agendamento criado!");
    setDate(undefined);
  };

  const handleRemove = (id: string) => {
    saveSchedules(schedules.filter((s) => s.id !== id));
    toast.success("Agendamento removido");
  };

  const handleToggle = (id: string) => {
    saveSchedules(
      schedules.map((s) => (s.id === id ? { ...s, enabled: !s.enabled } : s))
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
          <CalendarClock className="h-6 w-6 text-primary" /> Agendamento
        </h1>
        <p className="text-sm text-muted-foreground">
          Agende datas e horários para o funcionamento automático do motor.
        </p>
      </div>

      {/* Add Schedule Form */}
      <Card className="border-border/50">
        <CardHeader>
          <CardTitle className="text-base">Novo Agendamento</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-4 items-end">
            <div className="space-y-2">
              <Label>Data</Label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    className={cn(
                      "w-[220px] justify-start text-left font-normal",
                      !date && "text-muted-foreground"
                    )}
                  >
                    <CalendarIcon className="mr-2 h-4 w-4" />
                    {date ? format(date, "dd/MM/yyyy", { locale: ptBR }) : "Selecione a data"}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="single"
                    selected={date}
                    onSelect={setDate}
                    disabled={(d) => d < new Date(new Date().setHours(0, 0, 0, 0))}
                    initialFocus
                    className={cn("p-3 pointer-events-auto")}
                  />
                </PopoverContent>
              </Popover>
            </div>

            <div className="space-y-2">
              <Label>Hora Início</Label>
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <Input
                  type="time"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                  className="w-[130px]"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Hora Fim</Label>
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <Input
                  type="time"
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                  className="w-[130px]"
                />
              </div>
            </div>

            <Button onClick={handleAdd} className="gap-2">
              <Plus className="h-4 w-4" /> Agendar
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Schedule List */}
      <Card className="border-border/50">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <CalendarIcon className="h-4 w-4" /> Agendamentos ({schedules.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {schedules.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              Nenhum agendamento criado. Adicione um acima.
            </p>
          ) : (
            <div className="space-y-3">
              {schedules.map((s) => (
                <div
                  key={s.id}
                  className={cn(
                    "flex items-center justify-between rounded-lg border p-3 transition-colors",
                    s.enabled
                      ? "border-primary/20 bg-primary/5"
                      : "border-border/50 bg-muted/30 opacity-60"
                  )}
                >
                  <div className="flex items-center gap-4">
                    <Switch
                      checked={s.enabled}
                      onCheckedChange={() => handleToggle(s.id)}
                    />
                    <div>
                      <p className="text-sm font-medium text-foreground">
                        {format(new Date(s.date), "EEEE, dd 'de' MMMM 'de' yyyy", { locale: ptBR })}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {s.startTime} — {s.endTime}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={s.enabled ? "default" : "secondary"} className="gap-1">
                      <Power className="h-3 w-3" />
                      {s.enabled ? "Ativo" : "Inativo"}
                    </Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleRemove(s.id)}
                      className="h-8 w-8 text-destructive hover:text-destructive"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
