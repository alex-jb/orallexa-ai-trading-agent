import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DailyIntelView } from "../components/daily-intel";
import type { DailyIntelData } from "../types";
import { T } from "../types";

const t = T.EN;

const mockData: DailyIntelData = {
  date: "2026-04-02",
  generated_at: "2026-04-02T09:30:00Z",
  market_mood: "Risk-On",
  summary: "Markets rallied on strong earnings",
  gainers: [
    { ticker: "NVDA", price: 890, change_pct: 5.2, volume: 50000000 },
    { ticker: "AAPL", price: 195, change_pct: 2.1, volume: 30000000 },
  ],
  losers: [
    { ticker: "TSLA", price: 170, change_pct: -3.5, volume: 40000000 },
  ],
  sectors: [
    { sector: "Technology", etf: "XLK", change_pct: 2.8 },
    { sector: "Energy", etf: "XLE", change_pct: -1.2 },
  ],
  headlines: [
    { title: "NVDA crushes estimates", ticker: "NVDA", sentiment: "bullish", score: 0.8, url: "https://example.com", provider: "Reuters" },
  ],
  ai_picks: [
    { ticker: "AMD", direction: "bullish", reason: "Chip demand surge", catalyst: "Data center growth" },
  ],
};

describe("DailyIntelView — loading state", () => {
  it("shows skeleton placeholders when data is null", () => {
    const { container } = render(
      <DailyIntelView data={null} onSelectTicker={() => {}} t={t} zh={false} />
    );
    const skeletons = container.querySelectorAll(".skeleton");
    expect(skeletons.length).toBe(4);
  });
});

describe("DailyIntelView — with data", () => {
  it("shows market mood", () => {
    render(<DailyIntelView data={mockData} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText("RISK-ON")).toBeInTheDocument();
  });

  it("shows date", () => {
    render(<DailyIntelView data={mockData} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText("2026-04-02")).toBeInTheDocument();
  });

  it("shows morning brief summary", () => {
    render(<DailyIntelView data={mockData} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText("Markets rallied on strong earnings")).toBeInTheDocument();
  });

  it("shows gainers", () => {
    render(<DailyIntelView data={mockData} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText("+5.2%")).toBeInTheDocument();
  });

  it("shows losers", () => {
    render(<DailyIntelView data={mockData} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText("TSLA")).toBeInTheDocument();
    expect(screen.getByText("-3.5%")).toBeInTheDocument();
  });

  it("shows sectors", () => {
    render(<DailyIntelView data={mockData} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText("Technology")).toBeInTheDocument();
    expect(screen.getByText("+2.8%")).toBeInTheDocument();
    expect(screen.getByText("Energy")).toBeInTheDocument();
    expect(screen.getByText("-1.2%")).toBeInTheDocument();
  });

  it("shows AI picks", () => {
    render(<DailyIntelView data={mockData} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText("AMD")).toBeInTheDocument();
    expect(screen.getByText("Chip demand surge")).toBeInTheDocument();
  });

  it("shows headlines", () => {
    render(<DailyIntelView data={mockData} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText("NVDA crushes estimates")).toBeInTheDocument();
  });

  it("calls onSelectTicker when clicking a gainer", () => {
    const onSelect = vi.fn();
    render(<DailyIntelView data={mockData} onSelectTicker={onSelect} t={t} zh={false} />);
    fireEvent.click(screen.getByText("NVDA"));
    expect(onSelect).toHaveBeenCalledWith("NVDA");
  });

  it("calls onSelectTicker when clicking an AI pick", () => {
    const onSelect = vi.fn();
    render(<DailyIntelView data={mockData} onSelectTicker={onSelect} t={t} zh={false} />);
    fireEvent.click(screen.getByText("AMD"));
    expect(onSelect).toHaveBeenCalledWith("AMD");
  });

  it("shows last updated time", () => {
    render(<DailyIntelView data={mockData} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText(/09:30/)).toBeInTheDocument();
  });
});

describe("DailyIntelView — Risk-Off mood", () => {
  it("shows RISK-OFF in red", () => {
    const riskOff = { ...mockData, market_mood: "Risk-Off" };
    render(<DailyIntelView data={riskOff} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText("RISK-OFF")).toBeInTheDocument();
  });
});

describe("DailyIntelView — volume spikes", () => {
  it("shows volume spikes section", () => {
    const withVolume = {
      ...mockData,
      volume_spikes: [{ ticker: "GME", price: 25, change_pct: 12.5, volume_ratio: 8 }],
    };
    render(<DailyIntelView data={withVolume} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText("GME")).toBeInTheDocument();
    expect(screen.getByText("8x vol")).toBeInTheDocument();
  });
});

describe("DailyIntelView — orallexa thread", () => {
  it("shows thread posts", () => {
    const withThread = {
      ...mockData,
      orallexa_thread: ["Markets are looking strong today", "Tech leading the way"],
    };
    render(<DailyIntelView data={withThread} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText("Markets are looking strong today")).toBeInTheDocument();
    expect(screen.getByText("Tech leading the way")).toBeInTheDocument();
  });
});

describe("DailyIntelView — macro pulse", () => {
  it("shows macro indicators when provided", () => {
    const withMacro = {
      ...mockData,
      macro: [
        { label: "VIX", value: "14.2", change: -1.8, direction: "down" as const },
        { label: "BTC", value: "$91,200", change: 3.2, direction: "up" as const },
      ],
    };
    render(<DailyIntelView data={withMacro} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText("VIX")).toBeInTheDocument();
    expect(screen.getByText("14.2")).toBeInTheDocument();
    expect(screen.getByText("BTC")).toBeInTheDocument();
    expect(screen.getByText("$91,200")).toBeInTheDocument();
  });

  it("does not render macro section when absent", () => {
    render(<DailyIntelView data={mockData} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.queryByText("Macro Pulse")).not.toBeInTheDocument();
  });
});

describe("DailyIntelView — fear & greed", () => {
  it("shows fear & greed gauge when provided", () => {
    const withFG = {
      ...mockData,
      fear_greed: {
        score: 68,
        label: "Greed",
        components: [
          { name: "Market Momentum", value: 74, signal: "greed" as const },
          { name: "Volatility", value: 78, signal: "greed" as const },
        ],
      },
    };
    render(<DailyIntelView data={withFG} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getAllByText("Greed").length).toBeGreaterThan(0);
    expect(screen.getByText("68")).toBeInTheDocument();
    expect(screen.getByText("Market Momentum")).toBeInTheDocument();
  });
});

describe("DailyIntelView — market breadth", () => {
  it("shows breadth panel when provided", () => {
    const withBreadth = {
      ...mockData,
      breadth: { advancers: 1842, decliners: 1156, unchanged: 87, new_highs: 124, new_lows: 38, adv_vol: 6800000000, dec_vol: 3200000000 },
    };
    render(<DailyIntelView data={withBreadth} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText(/1842/)).toBeInTheDocument();
    expect(screen.getByText(/1156/)).toBeInTheDocument();
    expect(screen.getByText("124")).toBeInTheDocument();
    expect(screen.getByText("38")).toBeInTheDocument();
  });
});

describe("DailyIntelView — options flow", () => {
  it("shows options flow entries when provided", () => {
    const withOptions = {
      ...mockData,
      options_flow: [
        { ticker: "NVDA", type: "call" as const, premium: "$12.4M", strike: "$150", expiry: "Apr 18", sentiment: "bullish" as const, unusual: true },
        { ticker: "TSLA", type: "put" as const, premium: "$8.7M", strike: "$250", expiry: "Apr 11", sentiment: "bearish" as const, unusual: false },
      ],
    };
    render(<DailyIntelView data={withOptions} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText("$12.4M")).toBeInTheDocument();
    expect(screen.getByText("CALL")).toBeInTheDocument();
    expect(screen.getByText("PUT")).toBeInTheDocument();
    expect(screen.getByText("$150")).toBeInTheDocument();
  });

  it("calls onSelectTicker when clicking an options flow entry", () => {
    const onSelect = vi.fn();
    const withOptions = {
      ...mockData,
      options_flow: [
        { ticker: "AMD", type: "call" as const, premium: "$4.8M", strike: "$140", expiry: "Apr 25", sentiment: "bullish" as const, unusual: true },
      ],
    };
    render(<DailyIntelView data={withOptions} onSelectTicker={onSelect} t={t} zh={false} />);
    fireEvent.click(screen.getByText("$4.8M"));
    expect(onSelect).toHaveBeenCalledWith("AMD");
  });
});

describe("DailyIntelView — economic calendar", () => {
  it("shows calendar events when provided", () => {
    const withCal = {
      ...mockData,
      econ_calendar: [
        { date: new Date().toISOString().slice(0, 10), time: "08:30", event: "CPI (MoM)", impact: "high" as const, forecast: "0.3%", previous: "0.4%" },
      ],
    };
    render(<DailyIntelView data={withCal} onSelectTicker={() => {}} t={t} zh={false} />);
    expect(screen.getByText("CPI (MoM)")).toBeInTheDocument();
    expect(screen.getByText("08:30")).toBeInTheDocument();
    expect(screen.getByText(/0\.3%/)).toBeInTheDocument();
  });
});
