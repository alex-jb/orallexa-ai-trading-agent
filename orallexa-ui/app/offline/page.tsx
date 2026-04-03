"use client";

import { useEffect, useState } from "react";

export default function OfflinePage() {
  const [checking, setChecking] = useState(false);
  const [lastSeen, setLastSeen] = useState<string | null>(null);

  useEffect(() => {
    // Show when the user was last online
    const ts = localStorage.getItem("orallexa_last_online");
    if (ts) setLastSeen(ts);
  }, []);

  const handleRetry = () => {
    setChecking(true);
    // Test connectivity
    fetch("/api/status", { cache: "no-store" })
      .then((r) => {
        if (r.ok) {
          window.location.href = "/";
        } else {
          setChecking(false);
        }
      })
      .catch(() => setChecking(false));
  };

  return (
    <main
      className="flex min-h-screen flex-col items-center justify-center px-6"
      style={{ background: "var(--bg-deep, #0A0A0F)" }}
    >
      {/* Art Deco decorative frame */}
      <div
        className="relative flex flex-col items-center px-12 py-10"
        style={{
          border: "1px solid var(--border-gold, rgba(212,175,55,0.25))",
          background: "var(--bg-card, #1A1A2E)",
          maxWidth: 480,
          width: "100%",
        }}
      >
        {/* Gold accent line */}
        <div
          className="absolute top-0 left-0 right-0 h-[2px]"
          style={{
            background:
              "linear-gradient(90deg, transparent, #D4AF37, #FFD700, #C5A255, transparent)",
          }}
        />

        {/* Corner ornaments */}
        {(["top-left", "top-right", "bottom-left", "bottom-right"] as const).map(
          (corner) => (
            <span
              key={corner}
              className="absolute w-4 h-4"
              style={{
                borderColor: "var(--gold, #D4AF37)",
                ...(corner.includes("top") ? { top: 6 } : { bottom: 6 }),
                ...(corner.includes("left")
                  ? { left: 6, borderLeft: "2px solid", borderTop: corner === "top-left" ? "2px solid" : "none", borderBottom: corner === "bottom-left" ? "2px solid" : "none" }
                  : { right: 6, borderRight: "2px solid", borderTop: corner === "top-right" ? "2px solid" : "none", borderBottom: corner === "bottom-right" ? "2px solid" : "none" }),
              }}
            />
          )
        )}

        {/* Diamond motif */}
        <div className="flex items-center gap-2 mb-6">
          <span
            className="block w-2 h-2 rotate-45"
            style={{ background: "var(--gold, #D4AF37)" }}
          />
          <span
            className="block w-3 h-3 rotate-45"
            style={{
              border: "1.5px solid var(--gold-bright, #FFD700)",
              background: "transparent",
            }}
          />
          <span
            className="block w-2 h-2 rotate-45"
            style={{ background: "var(--gold, #D4AF37)" }}
          />
        </div>

        {/* Heading */}
        <h1
          className="text-center text-2xl font-semibold tracking-[0.12em] uppercase mb-2"
          style={{
            fontFamily: "var(--font-josefin, 'Josefin Sans', sans-serif)",
            background: "linear-gradient(135deg, #D4AF37, #FFD700, #C5A255)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}
        >
          You&apos;re Offline
        </h1>

        {/* Chinese subtitle */}
        <p
          className="text-center text-sm tracking-wide mb-6"
          style={{
            fontFamily: "var(--font-josefin, 'Josefin Sans', sans-serif)",
            color: "var(--text-muted-safe, #8B8E96)",
          }}
        >
          您目前处于离线状态
        </p>

        {/* Divider */}
        <div className="flex items-center gap-3 w-full mb-6">
          <div
            className="flex-1 h-px"
            style={{
              background:
                "linear-gradient(90deg, transparent, var(--gold, #D4AF37))",
            }}
          />
          <span
            className="block w-1.5 h-1.5 rotate-45"
            style={{ background: "var(--gold-muted, #C5A255)" }}
          />
          <div
            className="flex-1 h-px"
            style={{
              background:
                "linear-gradient(90deg, var(--gold, #D4AF37), transparent)",
            }}
          />
        </div>

        {/* Body text */}
        <p
          className="text-center text-sm leading-relaxed mb-1"
          style={{
            fontFamily: "var(--font-lato, 'Lato', sans-serif)",
            color: "var(--champagne, #F5E6CA)",
          }}
        >
          Check your connection and try again.
        </p>
        <p
          className="text-center text-xs leading-relaxed mb-4"
          style={{
            fontFamily: "var(--font-lato, 'Lato', sans-serif)",
            color: "var(--text-muted-safe, #8B8E96)",
          }}
        >
          请检查您的网络连接，然后重试。
        </p>

        {/* Last online timestamp */}
        {lastSeen && (
          <p
            className="text-center text-[10px] mb-6"
            style={{
              fontFamily: "var(--font-dm-mono, 'DM Mono', monospace)",
              color: "var(--text-muted-safe, #8B8E96)",
            }}
          >
            Last online: {lastSeen}
          </p>
        )}

        {/* Cached data hint */}
        <p
          className="text-center text-[10px] mb-6 px-4"
          style={{
            fontFamily: "var(--font-lato, 'Lato', sans-serif)",
            color: "var(--gold-muted, #C5A255)",
          }}
        >
          Previously viewed data may still be available from cache.
        </p>

        {/* Retry button */}
        <button
          type="button"
          onClick={handleRetry}
          disabled={checking}
          className="px-8 py-2.5 text-xs font-semibold uppercase tracking-[0.2em] transition-colors duration-[120ms] cursor-pointer disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#FFD700] focus-visible:outline-offset-2"
          style={{
            fontFamily: "var(--font-josefin, 'Josefin Sans', sans-serif)",
            background: "var(--gold, #D4AF37)",
            color: "var(--bg-deep, #0A0A0F)",
            border: "none",
            borderRadius: 0,
          }}
        >
          {checking ? "Checking... / 检测中..." : "Retry / 重试"}
        </button>

        {/* Go to cached dashboard */}
        <a
          href="/"
          className="mt-3 text-[10px] uppercase tracking-[0.14em] transition-colors hover:text-[#FFD700]"
          style={{
            fontFamily: "var(--font-josefin, 'Josefin Sans', sans-serif)",
            color: "var(--gold-muted, #C5A255)",
            textDecoration: "none",
          }}
        >
          View cached dashboard / 查看缓存数据
        </a>

        {/* Bottom accent line */}
        <div
          className="absolute bottom-0 left-0 right-0 h-[2px]"
          style={{
            background:
              "linear-gradient(90deg, transparent, #C5A255, #D4AF37, #C5A255, transparent)",
          }}
        />
      </div>

      {/* Brand footer */}
      <p
        className="mt-8 text-[9px] uppercase tracking-[0.28em]"
        style={{
          fontFamily: "var(--font-josefin, 'Josefin Sans', sans-serif)",
          color: "var(--text-dim, #6A6D75)",
        }}
      >
        Orallexa Capital Intelligence
      </p>
    </main>
  );
}
