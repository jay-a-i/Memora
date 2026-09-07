import { useRef, useState } from "react";
import { toast } from "sonner";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface PdfUploaderProps {
  onUpload: (file: File) => Promise<{ chunks_count: number }>;
}

export function PdfUploader({ onUpload }: PdfUploaderProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  const handleSubmit = async () => {
    if (!file || uploading) return;
    setUploading(true);
    try {
      const { chunks_count } = await onUpload(file);
      toast.success(`Uploaded — ${chunks_count} chunks`);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <Input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="cursor-pointer"
      />
      <Button
        onClick={handleSubmit}
        disabled={!file || uploading}
        className="w-full"
        size="sm"
      >
        <Upload className="h-4 w-4" />
        {uploading ? "Uploading…" : "Upload PDF"}
      </Button>
    </div>
  );
}
