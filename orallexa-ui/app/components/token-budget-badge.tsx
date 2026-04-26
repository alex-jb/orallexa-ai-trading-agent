"use client";

import type { TokenBudgetSnapshot } from "../types";

/**
 * Compact strip rendering the token_budget snapshot returned by
 * /api/deep-analysis when the caller passed token_cap or cost_cap_usd.
 *
 * Layout: usage bar + text triplet + "skipped" pills if any. Stays
 * inline with surrounding content; no Mod wrapper, no border.
 */
export function TokenBudgetBadge({
  budget,
  skipped,
  t,
  zh,
}: {
  budget: TokenBudgetSnapshot | null;
  skipped?: string[] | null;
  t: Record<string, string>;
  zh: boolean;
}) {
  if (!budget) return null;

  const tokenPct =
    budget.cap_tokens && budget.cap_tokens > 0
      ? Math.min(100, (budget.used_tokens / budget.cap_tokens) * 100)
      : 0;
  const usdPct =
    budget.cap_usd && budget.cap_usd > 0
      ? Math.min(100, (budget.used_cost_usd / budget.cap_usd) * 100)
      : 0;
  const pct = Math.max(tokenPct, usdPct);

  const color =
    budget.exhausted ? "#8B0000"
    : pct > 80 ? "#D4AF37"
    : "#006B3F";

  return (
    <div
      className="flex flex-col gap-1.5 px-3 py-2 mb-2"
      style={{
        background: `${color}10`,
        border: `1px solid ${color}30`,
      }}
      role="status"
      aria-label="Token budget"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em] text-[#8B8E96]">
          {t.tokenBudget || (zh ? "Token 预算" : "Token Budget")}
        </span>
        <div className="flex items-center gap-3 text-[9px] font-[DM_Mono]">
          {budget.cap_tokens !== null && (
            <span style={{ color }}>
              {budget.used_tokens.toLocaleString()} / {budget.cap_tokens.toLocaleString()}{" "}
              <span className="text-[#6B6E76]">tok</span>
            </span>
          )}
          {budget.cap_usd !== null && (
            <span style={{ color }}>
              ${budget.used_cost_usd.toFixed(4)} / ${budget.cap_usd.toFixed(2)}
            </span>
          )}
          {budget.exhausted && (
            <span
              className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] px-1.5 py-0.5"
              style={{ background: "rgba(139,0,0,0.15)", color: "#8B0000" }}
            >
              {t.budgetExhausted || (zh ? "超额" : "exhausted")}
            </span>
          )}
        </div>
      </div>

      {/* Usage bar */}
      <div className="relative h-[3px] w-full" style={{ background: "rgba(42,42,62,0.6)" }}>
        <div
          className="absolute top-0 bottom-0 left-0 transition-all"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>

      {/* Skipped steps (if any) */}
      {skipped && skipped.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 mt-0.5">
          <span className="text-[7px] font-[Josefin_Sans] uppercase tracking-[0.14em] text-[#8B8E96]">
            {t.budgetSkipped || (zh ? "跳过" : "skipped")}:
          </span>
          {skipped.map((s) => (
            <span
              key={s}
              className="text-[8px] font-[DM_Mono] px-1.5 py-0.5"
              style={{
                background: "rgba(212,175,55,0.10)",
                border: "1px solid rgba(212,175,55,0.20)",
                color: "#D4AF37",
              }}
            >
              {s.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
