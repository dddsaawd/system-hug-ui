import { useRef } from "react";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

interface FileUploadButtonProps {
  label: string;
  accept?: string;
  disabled?: boolean;
  onFileLoaded: (content: string, fileName: string) => void;
}

export function FileUploadButton({ label, accept = ".txt", disabled, onFileLoaded }: FileUploadButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 5 * 1024 * 1024) {
      toast.error("Arquivo muito grande (máx 5MB)");
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const text = reader.result as string;
      onFileLoaded(text, file.name);
      toast.success(`${file.name} carregado com sucesso!`);
    };
    reader.onerror = () => toast.error("Erro ao ler arquivo");
    reader.readAsText(file);

    // Reset input so same file can be re-uploaded
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={handleChange}
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="gap-1.5"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      >
        <Upload className="h-3.5 w-3.5" />
        {label}
      </Button>
    </>
  );
}
