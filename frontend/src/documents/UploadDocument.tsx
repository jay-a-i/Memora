import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { Button } from '../components/ui/Button';
import { IconUpload } from '../components/ui/Icon';
import { ACCEPTED_UPLOAD_ATTRIBUTE } from '../config';

/**
 * Upload control.
 *
 * A file input driven by a styled button, plus a drop zone on the drop target.
 * Accepts only the extensions the backend allows, so an unsupported file is
 * filtered by the OS dialog before it ever reaches the network.
 */

interface UploadDocumentProps {
  onUpload: (file: File) => Promise<boolean>;
  uploading: boolean;
  disabled?: boolean;
}

export function UploadDocument({ onUpload, uploading, disabled = false }: UploadDocumentProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  async function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    await onUpload(file);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (uploading || disabled) return;
    void handleFiles(event.dataTransfer.files);
  }

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    void handleFiles(event.target.files);
    // Reset so re-picking the same file still fires a change event.
    event.target.value = '';
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!uploading && !disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`px-2 pb-2 pt-1 transition-colors ${
        dragging ? 'bg-grey-150 outline outline-1 -outline-offset-2 outline-grey-400' : ''
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_UPLOAD_ATTRIBUTE}
        onChange={onChange}
        disabled={uploading || disabled}
        className="sr-only"
        aria-label="Choose a document to upload"
      />

      <Button
        variant="outline"
        size="sm"
        onClick={() => inputRef.current?.click()}
        disabled={uploading || disabled}
        icon={<IconUpload className="h-3.5 w-3.5" />}
        className="w-full border-dashed"
      >
        {uploading ? 'Uploading' : 'Upload document'}
      </Button>

      <p className="mt-1.5 px-0.5 text-[10px] leading-relaxed text-grey-400">
        PDF, TXT, Markdown or DOCX. Drag a file here.
      </p>
    </div>
  );
}
