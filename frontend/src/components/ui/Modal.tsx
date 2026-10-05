import { useEffect, useRef, type ReactNode } from 'react';
import { IconClose } from './Icon';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
}

/** Elements that can receive focus, used by the trap. */
const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Accessible dialog: focus moves in on open, is trapped while open, Escape
 * closes, and focus returns to the trigger on close. Background scroll is
 * locked for the duration.
 */
export function Modal({ open, onClose, title, description, children }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  // Read through a ref rather than listed as an effect dependency. Call sites
  // pass an inline arrow, so its identity changed on every parent render; the
  // effect then re-ran, its cleanup restored focus to the row's trigger, and
  // the next frame pulled focus back to the first button -- stealing focus
  // away from the confirm button roughly every time the parent re-rendered.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;

    previouslyFocused.current = document.activeElement as HTMLElement | null;

    const { overflow } = document.body.style;
    document.body.style.overflow = 'hidden';

    // Defer to the next frame so the panel is mounted and focusable.
    const raf = requestAnimationFrame(() => {
      const first = panelRef.current?.querySelector<HTMLElement>(FOCUSABLE);
      (first ?? panelRef.current)?.focus();
    });

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab') return;

      const focusable = Array.from(
        panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [],
      ).filter((el) => el.offsetParent !== null);
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener('keydown', onKeyDown, true);
      document.body.style.overflow = overflow;
      previouslyFocused.current?.focus?.();
    };
    // Keyed on `open` alone: the dialog should set up focus once when it opens
    // and tear it down once when it closes, not on every parent render.
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-grey-950/25"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="relative w-full max-w-md rounded-lg border border-grey-300 bg-grey-25 shadow-[0_16px_40px_-12px_rgb(22_22_22/0.25)] focus:outline-none"
      >
        <header className="flex items-start justify-between gap-4 border-b border-grey-200 px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-grey-900">{title}</h2>
            {description && (
              <p className="mt-1 text-xs leading-relaxed text-grey-500">{description}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="-mr-1 -mt-1 rounded p-1 text-grey-500 transition-colors hover:bg-grey-150 hover:text-grey-900"
          >
            <IconClose className="h-4 w-4" />
          </button>
        </header>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}
