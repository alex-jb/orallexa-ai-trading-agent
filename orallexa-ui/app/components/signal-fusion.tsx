"use client";

import type { SignalFusion } from "../types";
import { Mod } from "./atoms";

const SOURCE_LABELS: Record<string, { en: string; zh: string; icon: string }> = {
  technical:          { en: "Technical",         zh: "技术面",     icon: "📈" },
  ml_ensemble:        { en: "ML Ensemble",       zh: "ML集成",    icon: "🤖" },
  news_sentiment:     { en: "News",              zh: "新闻情绪",   icon: "📰" },
  options_flow:       { en: "Options",           zh: "期权异动",   icon: "🎯" },
  institutional:      { en: "Institutional",     zh: "机构",      icon: "🏦" },
  social_sentiment:   { en: "Social",            zh: "社交情绪",   icon: "💬" },
  earnings:           { en: "Earnings",          zh: "财报",      icon: "📅" },
  prediction_markets: { en: "Prediction Markets", zh: "预测市场",   icon: "🔮" },
};

function ScoreBar({ score, weight }: { score: number; weight: number }) {
  const color = score > 10 ? "#006B3F" : score < -10 ? "#8B0000" : "#D4AF37";
  const barLeft = score >= 0 ? 50 : 50 + score / 2;
  const barWidth = Math.abs(score) / 2;
  const opacity = Math.max(0.3, weight);

  return (
    <div className="relative h-2 w-full" style={{ background: "rgba(42,42,62,0.6)" }}>
      <div className="absolute top-0 bottom-0 w-px left-1/2" style={{ background: "rgba(212,175,55,0.2)" }} />
      <div
        className="absolute top-0 bottom-0 transition-all duration-500"
        style={{
          left: `${barLeft}%`,
          width: `${barWidth}%`,
          background: color,
          opacity,
        }}
      />
    </div>
  );
}

export function SignalFusionCard({ fusion, t, zh }: {
  fusion: SignalFusion | null; t: Record<string, string>; zh: boolean;
}) {
  if (!fusion || !fusion.sources || fusion.n_sources === 0) return null;

  const convColor = fusion.conviction > 15 ? "#006B3F" : fusion.conviction < -15 ? "#8B0000" : "#D4AF37";
  const convBg = fusion.conviction > 15 ? "rgba(0,107,63,0.08)" : fusion.conviction < -15 ? "rgba(139,0,0,0.08)" : "rgba(212,175,55,0.06)";

  return (
    <Mod title={t.signalFusion}>
      {/* Conviction header */}
      <div className="flex items-center justify-between mb-3 px-2 py-2" style={{ background: convBg }}>
        <div>
          <span className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#8B8E96] mr-2">
            {t.fusionConviction}
          </span>
          <span className="text-[18px] font-[DM_Mono] font-bold" style={{ color: convColor }}>
            {fusion.conviction > 0 ? "+" : ""}{fusion.conviction}
          </span>
        </div>
        <div className="flex flex-col items-end">
          <span className="text-[10px] font-[Josefin_Sans] font-bold uppercase" style={{ color: convColor }}>
            {fusion.direction}
          </span>
          <span className="text-[8px] font-[DM_Mono] text-[#8B8E96]">
            {fusion.n_sources} {zh ? "个来源" : "sources"} · {fusion.confidence}% {zh ? "一致" : "agree"}
          </span>
        </div>
      </div>

      {/* Per-source breakdown */}
      <div className="space-y-2">
        {Object.entries(fusion.sources)
          .filter(([, s]) => s.available)
          .sort(([, a], [, b]) => Math.abs(b.score) - Math.abs(a.score))
          .map(([key, source]) => {
            const label = SOURCE_LABELS[key] || { en: key, zh: key, icon: "📊" };
            const scoreColor = source.score > 10 ? "#006B3F" : source.score < -10 ? "#8B0000" : "#D4AF37";

            return (
              <div key={key}>
                <div className="flex items-center justify-between mb-0.5">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px]">{label.icon}</span>
                    <span className="text-[9px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.1em] text-[#F5E6CA]">
                      {zh ? label.zh : label.en}
                    </span>
                    <span className="text-[7px] font-[DM_Mono] text-[#4A4D55]">
                      w={((source.normalized_weight || 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                  <span className="text-[11px] font-[DM_Mono] font-medium" style={{ color: scoreColor }}>
                    {source.score > 0 ? "+" : ""}{source.score}
                  </span>
                </div>
                <ScoreBar score={source.score} weight={source.normalized_weight || 0} />

                {/* Extra details for options */}
                {key === "options_flow" && source.pc_ratio !== undefined && (
                  <div className="flex gap-3 mt-0.5 pl-5">
                    <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">P/C: {source.pc_ratio}</span>
                    {source.max_pain && (
                      <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">
                        Max Pain: ${source.max_pain}
                      </span>
                    )}
                    {(source.unusual_calls?.length || 0) > 0 && (
                      <span className="text-[8px] font-[DM_Mono] text-[#006B3F]">
                        {source.unusual_calls!.length} unusual calls
                      </span>
                    )}
                    {(source.unusual_puts?.length || 0) > 0 && (
                      <span className="text-[8px] font-[DM_Mono] text-[#8B0000]">
                        {source.unusual_puts!.length} unusual puts
                      </span>
                    )}
                  </div>
                )}

                {/* Extra details for institutional */}
                {key === "institutional" && (
                  <div className="flex gap-3 mt-0.5 pl-5">
                    {source.short_pct !== undefined && source.short_pct > 0 && (
                      <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">
                        Short: {source.short_pct}%
                      </span>
                    )}
                    {(source.insider_transactions?.length || 0) > 0 && (
                      <span className="text-[8px] font-[DM_Mono] text-[#8B8E96]">
                        {source.insider_transactions!.length} insider txns
                      </span>
                    )}
                  </div>
                )}

                {/* Extra details for prediction markets */}
                {key === "prediction_markets" && (
                  <div className="pl-5 mt-0.5">
                    <div className="flex flex-wrap gap-3 mb-1">
                      {source.n_markets !== undefined && (
                        <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">
                          {source.n_markets} {zh ? "市场" : "markets"}
                          {source.n_directional !== undefined && ` (${source.n_directional} ${zh ? "方向性" : "directional"})`}
                        </span>
                      )}
                      {source.total_volume_24hr !== undefined && source.total_volume_24hr > 0 && (
                        <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">
                          Vol 24h: ${(source.total_volume_24hr / 1000).toFixed(1)}k
                        </span>
                      )}
                      {/* Platform breakdown — Polymarket / Kalshi pills */}
                      {source.n_by_platform && Object.entries(source.n_by_platform).map(([platform, n]) => (
                        <span
                          key={platform}
                          className="text-[7px] font-[Josefin_Sans] uppercase tracking-[0.12em] px-1 py-[1px]"
                          style={{
                            background: platform === "polymarket"
                              ? "rgba(94,53,177,0.12)"   // Polymarket purple
                              : platform === "kalshi"
                              ? "rgba(0,107,63,0.12)"    // Kalshi green
                              : "rgba(212,175,55,0.10)",
                            color: platform === "polymarket" ? "#A78BFA"
                              : platform === "kalshi" ? "#006B3F"
                              : "#C5A255",
                          }}
                        >
                          {platform} {n}
                        </span>
                      ))}
                    </div>
                    {source.markets && source.markets.length > 0 && (
                      <div className="space-y-0.5">
                        {source.markets.slice(0, 2).map((m, i) => {
                          const bullish = m.sign > 0;
                          const bearish = m.sign < 0;
                          const probColor = bullish ? "#006B3F" : bearish ? "#8B0000" : "#8B8E96";
                          const platformColor = m.platform === "polymarket" ? "#A78BFA"
                            : m.platform === "kalshi" ? "#006B3F"
                            : "#6B6E76";
                          return (
                            <div key={i} className="flex items-center gap-2">
                              <span className="text-[10px] font-[DM_Mono] font-medium shrink-0" style={{ color: probColor }}>
                                {Math.round(m.yes_price * 100)}%
                              </span>
                              {m.platform && (
                                <span
                                  className="text-[6px] font-[Josefin_Sans] uppercase tracking-[0.12em] shrink-0"
                                  style={{ color: platformColor }}
                                  title={`Source: ${m.platform}`}
                                >
                                  {m.platform.slice(0, 4)}
                                </span>
                              )}
                              <span className="text-[8px] font-[Lato] text-[#F5E6CA]/70 truncate" title={m.question}>
                                {m.question}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                {/* Extra details for earnings */}
                {key === "earnings" && source.days_until !== undefined && source.days_until !== null && (
                  <div className="flex gap-3 mt-0.5 pl-5">
                    <span className="text-[8px] font-[DM_Mono] text-[#D4AF37]">
                      {source.days_until}{zh ? "天后" : "d until"}
                    </span>
                    {source.avg_drift_5d !== undefined && source.avg_drift_5d !== null && (
                      <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">
                        PEAD: {source.avg_drift_5d >= 0 ? "+" : ""}{source.avg_drift_5d.toFixed(1)}%
                      </span>
                    )}
                    {source.positive_rate !== undefined && source.positive_rate !== null && (
                      <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">
                        {Math.round(source.positive_rate * 100)}% {zh ? "胜率" : "win"}
                      </span>
                    )}
                  </div>
                )}

                {/* Extra details for social sentiment */}
                {key === "social_sentiment" && source.n_posts !== undefined && source.n_posts > 0 && (
                  <div className="flex gap-3 mt-0.5 pl-5">
                    <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">
                      {source.n_posts} {zh ? "帖子" : "posts"}
                    </span>
                    {source.bullish !== undefined && source.bullish > 0 && (
                      <span className="text-[8px] font-[DM_Mono] text-[#006B3F]">
                        {source.bullish} {zh ? "看多" : "bull"}
                      </span>
                    )}
                    {source.bearish !== undefined && source.bearish > 0 && (
                      <span className="text-[8px] font-[DM_Mono] text-[#8B0000]">
                        {source.bearish} {zh ? "看空" : "bear"}
                      </span>
                    )}
                  </div>
                )}

                {/* Technical signals */}
                {key === "technical" && source.signals && source.signals.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-0.5 pl-5">
                    {source.signals.map((sig, i) => (
                      <span key={i} className="text-[7px] font-[DM_Mono] text-[#4A4D55] px-1 py-0.5"
                        style={{ background: "rgba(42,42,62,0.5)" }}>
                        {sig}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
      </div>
    </Mod>
  );
}
