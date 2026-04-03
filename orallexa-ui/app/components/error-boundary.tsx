"use client";

import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Log to console in dev, send to monitoring in prod
    console.error("[Orallexa Error]", error, info.componentStack);

    // If Sentry DSN is configured, report there
    // Sentry.captureException(error) — add when Sentry SDK is installed
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div
          className="min-h-screen flex items-center justify-center"
          style={{ background: "#0A0A0F" }}
        >
          <div className="text-center px-6 py-10" style={{ maxWidth: 420 }}>
            <div
              className="text-[10px] font-[Josefin_Sans] font-bold uppercase tracking-[0.28em] mb-4"
              style={{ color: "#8B0000" }}
            >
              System Error
            </div>
            <div
              className="text-[14px] font-[Lato] mb-6"
              style={{ color: "#F5E6CA" }}
            >
              Something went wrong. Please refresh the page.
            </div>
            <div
              className="text-[10px] font-[DM_Mono] mb-6 px-4 py-2 text-left overflow-auto"
              style={{
                color: "#8B8E96",
                background: "#1A1A2E",
                border: "1px solid rgba(139,0,0,0.3)",
                maxHeight: 120,
              }}
            >
              {this.state.error?.message || "Unknown error"}
            </div>
            <button
              onClick={() => window.location.reload()}
              className="px-6 py-2 text-[10px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.16em]"
              style={{
                background: "#D4AF37",
                color: "#0A0A0F",
                border: "none",
              }}
            >
              Reload / 重新加载
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
