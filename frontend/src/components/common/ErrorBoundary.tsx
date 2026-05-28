import React from 'react';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  resetKey?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info);
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="w-full max-w-md rounded-lg border border-border-subtle bg-brand-panel p-5 shadow-2xl shadow-black/20">
          <h2 className="text-sm font-semibold text-text-primary">Page failed to render</h2>
          <p className="mt-2 text-xs leading-5 text-text-secondary">
            Something in this view crashed. The rest of the dashboard is still available.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-4 h-9 rounded-md border border-border-strong bg-brand-base px-3 text-xs font-semibold text-text-primary hover:border-accent-amber"
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
