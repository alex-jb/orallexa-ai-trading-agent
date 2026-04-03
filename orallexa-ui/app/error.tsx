"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div
      className="flex min-h-screen items-center justify-center px-6"
      style={{ background: "var(--bg-deep, #0A0A0F)" }}
    >
      <div
        className="flex flex-col items-center px-10 py-8"
        style={{
          border: "1px solid rgba(139,0,0,0.3)",
          background: "var(--bg-card, #1A1A2E)",
          maxWidth: 440,
          width: "100%",
        }}
      >
        {/* Red accent */}
        <div
          className="w-full h-[2px] mb-6"
          style={{
            background: "linear-gradient(90deg, transparent, #8B0000, transparent)",
          }}
        />

        <h2
          className="text-lg font-semibold uppercase tracking-[0.12em] mb-2"
          style={{
            fontFamily: "var(--font-josefin, 'Josefin Sans', sans-serif)",
            color: "#8B0000",
          }}
        >
          System Error
        </h2>

        <p
          className="text-center text-sm mb-6"
          style={{
            fontFamily: "var(--font-lato, 'Lato', sans-serif)",
            color: "var(--text-muted-safe, #8B8E96)",
          }}
        >
          {error.message || "An unexpected error occurred."}
        </p>

        <button
          type="button"
          onClick={reset}
          className="px-6 py-2 text-xs font-semibold uppercase tracking-[0.16em] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#FFD700] focus-visible:outline-offset-2"
          style={{
            fontFamily: "var(--font-josefin, 'Josefin Sans', sans-serif)",
            background: "var(--gold, #D4AF37)",
            color: "var(--bg-deep, #0A0A0F)",
            border: "none",
            borderRadius: 0,
          }}
        >
          Try Again
        </button>
      </div>
    </div>
  );
}
