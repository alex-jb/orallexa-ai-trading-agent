"use client";

import { useState } from "react";
import type { MLModel } from "../types";
import { Mod } from "./atoms";

// Model purpose mapping (when not provided by backend)
const MODEL_PURPOSE: Record<string, { en: string; zh: string }> = {
  "Random Forest":        { en: "Core stock selection",     zh: "核心选股" },
  "Xgboost":              { en: "Gradient boosting",        zh: "梯度增强" },
  "Logistic Regression":  { en: "Baseline model",           zh: "基线对照" },
  "Emaformer":            { en: "Time series forecast",     zh: "时序预测" },
  "Chronos2":             { en: "Foundation model",         zh: "基础模型" },
  "Moirai2":              { en: "Zero-shot forecast",       zh: "零样本预测" },
  "Diffusion":            { en: "Probability paths",        zh: "概率路径" },
  "Gnn":                  { en: "Inter-stock signals",      zh: "关联信号" },
  "Rl Ppo":               { en: "Position optimization",    zh: "仓位优化" },
  "Buy & Hold":           { en: "Benchmark",                zh: "基准对比" },
};

function getPurpose(model: string, zh: boolean): string {
  const entry = MODEL_PURPOSE[model];
  if (entry) return zh ? entry.zh : entry.en;
  return zh ? "分析" : "Analysis";
}

function statusBadge(status?: string) {
  if (status === "failed") return { text: "FAILED", color: "#8B0000", bg: "rgba(139,0,0,0.1)" };
  if (status === "skipped") return { text: "SKIP", color: "#CD7F32", bg: "rgba(205,127,50,0.1)" };
  return { text: "LIVE", color: "#006B3F", bg: "rgba(0,107,63,0.1)" };
}

export function MLScoreboard({ models, zh }: { models: MLModel[]; zh?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  if (models.length === 0) return null;

  const activeModels = models.filter(m => m.status !== "failed" && m.status !== "skipped");
  const allModels = models;
  const best = activeModels.length > 0
    ? activeModels.filter(m => m.model !== "Buy & Hold").reduce((a, b) => a.sharpe > b.sharpe ? a : b, activeModels[0])
    : null;
  const liveCount = activeModels.filter(m => m.model !== "Buy & Hold").length;
  const totalCount = allModels.filter(m => m.model !== "Buy & Hold").length;
  const completionPct = totalCount > 0 ? Math.round((liveCount / totalCount) * 100) : 0;

  return (
    <Mod title={zh ? "AI 模型体系" : "AI MODEL SYSTEM"}>
      {/* Completion bar */}
      <div className="flex items-center gap-2 mb-3">
        <div className="flex-1 h-[6px] rounded-full overflow-hidden" style={{ background: "#2A2A3E" }}>
          <div className="h-full rounded-full transition-all" style={{ width: `${completionPct}%`, background: completionPct === 100 ? "#006B3F" : "linear-gradient(90deg, #D4AF37, #FFD700)" }} />
        </div>
        <span className="text-[9px] font-[DM_Mono] text-[#D4AF37]">{liveCount}/{totalCount} {zh ? "运行中" : "live"}</span>
        <span className="text-[9px] font-[DM_Mono] text-[#8B8E96]">{completionPct}%</span>
      </div>

      {/* Table header */}
      <div className="grid gap-0 text-[7px] font-[Josefin_Sans] text-[#8B8E96] uppercase tracking-[0.1em] pb-1.5 border-b mb-1"
        style={{ gridTemplateColumns: "1fr 50px 48px 48px 55px 60px", borderColor: "rgba(212,175,55,0.08)" }}>
        <span>{zh ? "模型" : "Model"}</span>
        <span className="text-center">{zh ? "状态" : "Status"}</span>
        <span className="text-right">Sharpe</span>
        <span className="text-right">{zh ? "收益" : "Return"}</span>
        <span className="text-right">{zh ? "胜率" : "Win%"}</span>
        <span className="text-right">{zh ? "用途" : "Purpose"}</span>
      </div>

      {/* Model rows */}
      {allModels.map((m, i) => {
        if (!expanded && m.model === "Buy & Hold") return null;
        const isBest = best && m.model === best.model;
        const badge = statusBadge(m.status);
        const isActive = m.status !== "failed" && m.status !== "skipped";
        return (
          <div key={i}
            className={`grid gap-0 py-[5px] border-b last:border-b-0 ${isBest ? "bg-[#D4AF37]/5" : ""}`}
            style={{ gridTemplateColumns: "1fr 50px 48px 48px 55px 60px", borderColor: "rgba(212,175,55,0.04)" }}
            title={m.error || ""}>
            <span className={`text-[9px] font-[Lato] truncate pr-1 ${isBest ? "text-[#D4AF37] font-semibold" : isActive ? "text-[#F5E6CA]/70" : "text-[#4A4D55]"}`}>
              {isBest && "★ "}{m.model}
            </span>
            <span className="flex justify-center">
              <span className="text-[6px] font-[DM_Mono] font-bold uppercase px-1 py-0.5 rounded-sm"
                style={{ color: badge.color, background: badge.bg }}>
                {badge.text}
              </span>
            </span>
            <span className={`text-[9px] font-[DM_Mono] text-right ${!isActive ? "text-[#4A4D55]" : m.sharpe > 0 ? "text-[#006B3F]" : "text-[#8B0000]"}`}>
              {isActive ? m.sharpe.toFixed(2) : "—"}
            </span>
            <span className={`text-[9px] font-[DM_Mono] text-right ${!isActive ? "text-[#4A4D55]" : m.return > 0 ? "text-[#006B3F]" : "text-[#8B0000]"}`}>
              {isActive ? `${m.return > 0 ? "+" : ""}${m.return.toFixed(1)}%` : "—"}
            </span>
            <span className={`text-[9px] font-[DM_Mono] text-right ${isActive ? "text-[#F5E6CA]/50" : "text-[#4A4D55]"}`}>
              {isActive ? `${m.win_rate.toFixed(0)}%` : "—"}
            </span>
            <span className="text-[7px] font-[Lato] text-[#8B8E96] text-right truncate">
              {m.purpose || getPurpose(m.model, !!zh)}
            </span>
          </div>
        );
      })}

      {/* Toggle + summary */}
      <div className="flex items-center justify-between mt-2 pt-2 border-t" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
        <button onClick={() => setExpanded(!expanded)}
          className="text-[8px] font-[Josefin_Sans] text-[#C5A255] hover:text-[#FFD700] uppercase tracking-[0.1em] transition-colors">
          {expanded ? (zh ? "收起" : "Collapse") : (zh ? "展开全部" : "Show All")}
        </button>
        {best && (
          <span className="text-[8px] font-[DM_Mono] text-[#D4AF37]">
            {zh ? "最优" : "Best"}: {best.model} (Sharpe {best.sharpe.toFixed(2)})
          </span>
        )}
      </div>
    </Mod>
  );
}
