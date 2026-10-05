/**
 * The blinking caret shown while assistant text is still arriving.
 *
 * Rendered inline after the final text node rather than as a block, so it
 * follows the end of the line and never reserves vertical space.
 */
export function StreamingCursor() {
  return (
    <span
      aria-hidden="true"
      className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[0.15em] animate-pulse-soft bg-grey-500 align-baseline"
    />
  );
}
