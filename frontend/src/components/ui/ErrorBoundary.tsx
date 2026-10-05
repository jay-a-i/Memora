import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Catches render-time failures so a single bad message cannot blank the app.
 *
 * Deliberately monochrome and self-contained: recovery is a reload, which
 * resets state that only the browser session holds.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Unhandled UI error', error, info.componentStack);
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="flex h-full items-center justify-center bg-grey-100 px-6">
        <div className="w-full max-w-sm rounded-lg border border-grey-300 bg-grey-25 px-5 py-5">
          <h1 className="text-sm font-semibold text-grey-900">Something went wrong</h1>
          <p className="mt-1.5 text-xs leading-relaxed text-grey-600">
            The interface hit an unexpected error. Reloading usually clears it.
          </p>
          <pre className="mt-3 overflow-x-auto rounded border border-grey-200 bg-grey-100 px-2.5 py-2 font-mono text-[11px] leading-relaxed text-grey-600">
            {error.message}
          </pre>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-4 w-full rounded-md border border-grey-900 bg-grey-900 px-3 py-2 text-xs font-medium text-grey-25 transition-colors hover:bg-grey-800"
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
