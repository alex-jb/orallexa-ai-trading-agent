import { describe, it, expect } from "vitest";
import {
  displayDec, subtitleDec, sigLabel, confLabel, riskLabel,
  decColor, riskColor, sentCls, recBg, nsSummary,
} from "../types";
import type { NewsItem } from "../types";

describe("displayDec", () => {
  it("maps BUY to BULLISH", () => expect(displayDec("BUY")).toBe("BULLISH"));
  it("maps SELL to BEARISH", () => expect(displayDec("SELL")).toBe("BEARISH"));
  it("maps WAIT to NEUTRAL", () => expect(displayDec("WAIT")).toBe("NEUTRAL"));
  it("passes through unknown values", () => expect(displayDec("HOLD")).toBe("HOLD"));
});

describe("subtitleDec", () => {
  it("returns English subtitle for BUY", () => expect(subtitleDec("BUY", false)).toBe("Bullish setup detected"));
  it("returns Chinese subtitle for BUY", () => expect(subtitleDec("BUY", true)).toBe("看涨信号"));
  it("returns English subtitle for SELL", () => expect(subtitleDec("SELL", false)).toBe("Bearish signal detected"));
  it("returns empty for unknown", () => expect(subtitleDec("HOLD", false)).toBe(""));
});

describe("sigLabel", () => {
  it("returns Very Strong for >= 80", () => expect(sigLabel(85)).toBe("Very Strong"));
  it("returns Strong for >= 65", () => expect(sigLabel(70)).toBe("Strong"));
  it("returns Moderate for >= 50", () => expect(sigLabel(55)).toBe("Moderate"));
  it("returns Weak for >= 35", () => expect(sigLabel(40)).toBe("Weak"));
  it("returns Very Weak for < 35", () => expect(sigLabel(20)).toBe("Very Weak"));
  it("handles boundary at 80", () => expect(sigLabel(80)).toBe("Very Strong"));
  it("handles boundary at 65", () => expect(sigLabel(65)).toBe("Strong"));
});

describe("confLabel", () => {
  it("returns High for >= 70", () => expect(confLabel(75)).toBe("High"));
  it("returns Moderate for >= 50", () => expect(confLabel(60)).toBe("Moderate"));
  it("returns Low for >= 30", () => expect(confLabel(35)).toBe("Low"));
  it("returns Very Low for < 30", () => expect(confLabel(10)).toBe("Very Low"));
});

describe("riskLabel", () => {
  it("maps LOW to Low", () => expect(riskLabel("LOW")).toBe("Low"));
  it("maps MEDIUM to Moderate", () => expect(riskLabel("MEDIUM")).toBe("Moderate"));
  it("maps HIGH to Elevated", () => expect(riskLabel("HIGH")).toBe("Elevated"));
  it("passes through unknown", () => expect(riskLabel("EXTREME")).toBe("EXTREME"));
});

describe("decColor", () => {
  it("returns emerald for BUY", () => expect(decColor("BUY")).toBe("#006B3F"));
  it("returns ruby for SELL", () => expect(decColor("SELL")).toBe("#8B0000"));
  it("returns gold for WAIT", () => expect(decColor("WAIT")).toBe("#D4AF37"));
});

describe("riskColor", () => {
  it("returns emerald for LOW", () => expect(riskColor("LOW")).toBe("#006B3F"));
  it("returns ruby for HIGH", () => expect(riskColor("HIGH")).toBe("#8B0000"));
  it("returns gold for MEDIUM", () => expect(riskColor("MEDIUM")).toBe("#D4AF37"));
});

describe("sentCls", () => {
  it("returns emerald class for bullish", () => expect(sentCls("bullish")).toContain("#006B3F"));
  it("returns ruby class for bearish", () => expect(sentCls("bearish")).toContain("#8B0000"));
  it("returns muted class for neutral", () => expect(sentCls("neutral")).toContain("#8B8E96"));
});

describe("recBg", () => {
  it("returns green bg for BUY", () => expect(recBg("BUY")).toContain("0,107,63"));
  it("returns red bg for SELL", () => expect(recBg("SELL")).toContain("139,0,0"));
  it("returns gold bg for WAIT", () => expect(recBg("WAIT")).toContain("212,175,55"));
});

describe("nsSummary", () => {
  it("returns bullish when avg score > 0.1", () => {
    const items: NewsItem[] = [
      { title: "Good news", sentiment: "bullish", score: 0.5 },
      { title: "Okay news", sentiment: "neutral", score: 0.1 },
    ];
    const result = nsSummary(items);
    expect(result.label).toBe("bullish");
    expect(result.color).toBe("#006B3F");
    expect(result.avg).toBeGreaterThan(0.1);
  });

  it("returns bearish when avg score < -0.1", () => {
    const items: NewsItem[] = [
      { title: "Bad news", sentiment: "bearish", score: -0.5 },
      { title: "Terrible news", sentiment: "bearish", score: -0.3 },
    ];
    const result = nsSummary(items);
    expect(result.label).toBe("bearish");
    expect(result.color).toBe("#8B0000");
  });

  it("returns neutral for balanced scores", () => {
    const items: NewsItem[] = [
      { title: "Meh", sentiment: "neutral", score: 0.05 },
      { title: "Also meh", sentiment: "neutral", score: -0.05 },
    ];
    const result = nsSummary(items);
    expect(result.label).toBe("neutral");
    expect(result.color).toBe("#8B8E96");
  });

  it("handles empty array", () => {
    const result = nsSummary([]);
    expect(result.label).toBe("neutral");
    expect(result.avg).toBe(0);
  });
});
