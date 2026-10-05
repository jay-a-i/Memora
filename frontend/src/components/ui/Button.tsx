import type { ButtonHTMLAttributes, ReactNode } from 'react';

/**
 * Monochrome button.
 *
 * Variants differ by background lightness and border weight, never by hue:
 * `solid` is the single primary action, `subtle` and `ghost` recede.
 */

type Variant = 'solid' | 'subtle' | 'ghost' | 'outline';
type Size = 'sm' | 'md';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** Rendered before the label; decorative, so hidden from assistive tech. */
  icon?: ReactNode;
}

const VARIANTS: Record<Variant, string> = {
  solid:
    'bg-grey-900 text-grey-25 border border-grey-900 hover:bg-grey-800 active:bg-grey-950 disabled:bg-grey-300 disabled:border-grey-300 disabled:text-grey-500',
  subtle:
    'bg-grey-150 text-grey-800 border border-grey-200 hover:bg-grey-200 hover:border-grey-300 active:bg-grey-250 disabled:text-grey-400 disabled:hover:bg-grey-150',
  outline:
    'bg-transparent text-grey-700 border border-grey-300 hover:bg-grey-100 hover:text-grey-900 active:bg-grey-150 disabled:text-grey-400 disabled:hover:bg-transparent',
  ghost:
    'bg-transparent text-grey-600 border border-transparent hover:bg-grey-150 hover:text-grey-900 active:bg-grey-200 disabled:text-grey-400 disabled:hover:bg-transparent',
};

const SIZES: Record<Size, string> = {
  sm: 'h-7 px-2.5 text-xs gap-1.5',
  md: 'h-9 px-3.5 text-sm gap-2',
};

export function Button({
  variant = 'subtle',
  size = 'md',
  icon,
  className = '',
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex shrink-0 items-center justify-center rounded-md font-medium transition-colors duration-150 disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...rest}
    >
      {icon}
      {children}
    </button>
  );
}
