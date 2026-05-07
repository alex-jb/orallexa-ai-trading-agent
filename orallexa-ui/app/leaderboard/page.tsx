/**
 * /leaderboard — public walk-forward Sharpe leaderboard.
 *
 * Pulls the curated EVAL_TABLE block out of the parent repo's
 * README.md (between EVAL_TABLE_START / EVAL_TABLE_END markers)
 * via GitHub raw on each build. Revalidates hourly.
 *
 * Why exists: 2026-05-07 fundraise prep. README.md is the canonical
 * source of out-of-sample Sharpe data, but it's buried under a fold
 * that VCs don't scroll to. A public /leaderboard URL with a
 * standalone, sharable view of the same data is a deck-ready slide
 * + a recurring dashboard a VC can revisit.
 *
 * Data flow: GitHub raw → markdown table → parsed in-page → rendered
 * with Art Deco styling per docs/DESIGN.md.
 */

const README_RAW =
  "https://raw.githubusercontent.com/alex-jb/orallexa-ai-trading-agent/master/README.md";

export const revalidate = 3600;
export const metadata = {
  title: "Walk-Forward Leaderboard — Orallexa",
  description:
    "Out-of-sample Sharpe ratios across 9 strategies × 10 tickers. Each pair tested against 3 independent statistical gates.",
};

type Row = {
  strategy: string;
  ticker: string;
  oosSharpe: number;
  verdict: "STRONG PASS" | "PASS" | "MARGINAL" | "FAIL" | string;
  pValue: number;
};

async function loadRows(): Promise<{ rows: Row[]; generatedAt: string }> {
  try {
    const res = await fetch(README_RAW, { next: { revalidate: 3600 } });
    if (!res.ok) throw new Error(`raw fetch ${res.status}`);
    const md = await res.text();

    const m = md.match(/<!-- EVAL_TABLE_START -->([\s\S]*?)<!-- EVAL_TABLE_END -->/);
    if (!m) return { rows: [], generatedAt: "—" };

    const block = m[1];
    const lines = block.split("\n").filter((l) => l.trim().startsWith("|"));
    const rows: Row[] = [];
    for (const line of lines) {
      const cells = line.split("|").map((c) => c.trim()).filter(Boolean);
      if (cells.length < 5) continue;
      if (cells[0].toLowerCase().startsWith("strategy")) continue; // header
      if (cells[0].includes("---")) continue; // separator
      const sharpe = parseFloat(cells[2].replace(/\*\*/g, ""));
      if (Number.isNaN(sharpe)) continue;
      rows.push({
        strategy: cells[0],
        ticker: cells[1],
        oosSharpe: sharpe,
        verdict: cells[3] as Row["verdict"],
        pValue: parseFloat(cells[4]),
      });
    }
    rows.sort((a, b) => b.oosSharpe - a.oosSharpe);

    // Try to extract last-updated marker from the report header.
    const tsMatch = md.match(/Generated: (\d{4}-\d{2}-\d{2})/);
    const generatedAt = tsMatch?.[1] || new Date().toISOString().slice(0, 10);
    return { rows, generatedAt };
  } catch {
    return { rows: [], generatedAt: "—" };
  }
}

export default async function LeaderboardPage() {
  const { rows, generatedAt } = await loadRows();

  const total = rows.length;
  const strongPass = rows.filter((r) => r.verdict.includes("STRONG")).length;
  const pass = rows.filter((r) => r.verdict === "PASS").length;
  const marginal = rows.filter((r) => r.verdict.includes("MARGINAL")).length;

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "var(--bg-deep, #0A0A0F)",
        color: "var(--champagne, #F5E6CA)",
        padding: "48px 24px",
      }}
    >
      <div style={{ maxWidth: 960, margin: "0 auto" }}>
        <header style={{ marginBottom: 40 }}>
          <p
            style={{
              fontFamily: "'Josefin Sans', sans-serif",
              fontSize: 9,
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--gold, #D4AF37)",
              marginBottom: 8,
            }}
          >
            ▸ Public Walk-Forward Leaderboard
          </p>
          <h1
            style={{
              fontFamily: "'Poiret One', serif",
              fontSize: 42,
              lineHeight: 1.1,
              margin: 0,
              background:
                "linear-gradient(135deg, #D4AF37, #FFD700, #C5A255)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            Out-of-Sample Sharpe
          </h1>
          <p
            style={{
              fontFamily: "Lato, sans-serif",
              fontSize: 14,
              marginTop: 12,
              color: "var(--text-muted-safe, #8B8E96)",
              maxWidth: 640,
            }}
          >
            Every strategy tested against 3 independent statistical gates: walk-forward
            (OOS Sharpe &gt; 0 in &gt;50% of windows), p-value &lt; 0.05, and Monte Carlo
            (&gt; 75th percentile). Live data, refreshed hourly from
            the public evaluation report.
          </p>
        </header>

        <section
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 12,
            marginBottom: 32,
          }}
        >
          <Stat label="Total pairs" value={total.toString()} />
          <Stat label="Strong pass" value={strongPass.toString()} accent="emerald" />
          <Stat label="Pass" value={pass.toString()} accent="gold" />
          <Stat label="Marginal" value={marginal.toString()} accent="bronze" />
        </section>

        {rows.length === 0 ? (
          <p style={{ color: "var(--text-muted, #6B6E76)", fontStyle: "italic" }}>
            Data unavailable — try again later.
          </p>
        ) : (
          <div
            style={{
              border: "1px solid var(--border-gold, rgba(212,175,55,0.25))",
              padding: 1,
            }}
          >
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontFamily: "Lato, sans-serif",
              }}
            >
              <thead>
                <tr
                  style={{
                    background: "var(--bg-panel, #0D1117)",
                  }}
                >
                  <Th>Rank</Th>
                  <Th>Strategy</Th>
                  <Th>Ticker</Th>
                  <Th align="right">OOS Sharpe</Th>
                  <Th align="right">p-value</Th>
                  <Th>Verdict</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr
                    key={`${r.strategy}-${r.ticker}`}
                    style={{
                      borderTop: "1px solid var(--border, #2A2A3E)",
                      background:
                        i % 2 === 0
                          ? "var(--bg-card, #1A1A2E)"
                          : "var(--bg-panel, #0D1117)",
                    }}
                  >
                    <Td>
                      <span
                        style={{
                          fontFamily: "'DM Mono', monospace",
                          fontSize: 12,
                          color: "var(--gold, #D4AF37)",
                        }}
                      >
                        {(i + 1).toString().padStart(2, "0")}
                      </span>
                    </Td>
                    <Td>
                      <span style={{ fontSize: 13 }}>{r.strategy}</span>
                    </Td>
                    <Td>
                      <span
                        style={{
                          fontFamily: "'DM Mono', monospace",
                          fontSize: 12,
                          color: "var(--ivory, #FAFAF0)",
                        }}
                      >
                        {r.ticker}
                      </span>
                    </Td>
                    <Td align="right">
                      <span
                        style={{
                          fontFamily: "'DM Mono', monospace",
                          fontSize: 14,
                          fontWeight: 500,
                          color:
                            r.oosSharpe >= 0.9
                              ? "var(--emerald, #006B3F)"
                              : r.oosSharpe >= 0.5
                              ? "var(--gold, #D4AF37)"
                              : r.oosSharpe >= 0
                              ? "var(--bronze, #CD7F32)"
                              : "var(--ruby, #8B0000)",
                        }}
                      >
                        {r.oosSharpe.toFixed(2)}
                      </span>
                    </Td>
                    <Td align="right">
                      <span
                        style={{
                          fontFamily: "'DM Mono', monospace",
                          fontSize: 12,
                          color: "var(--text-muted-safe, #8B8E96)",
                        }}
                      >
                        {r.pValue.toFixed(3)}
                      </span>
                    </Td>
                    <Td>
                      <VerdictPill verdict={r.verdict} />
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <footer
          style={{
            marginTop: 32,
            paddingTop: 16,
            borderTop: "1px solid var(--border, #2A2A3E)",
            display: "flex",
            justifyContent: "space-between",
            fontFamily: "'Josefin Sans', sans-serif",
            fontSize: 10,
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            color: "var(--text-muted-safe, #8B8E96)",
          }}
        >
          <span>Last update · {generatedAt}</span>
          <a
            href="https://github.com/alex-jb/orallexa-ai-trading-agent/blob/master/docs/evaluation_report.md"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "var(--gold, #D4AF37)", textDecoration: "none" }}
          >
            Full report ↗
          </a>
        </footer>
      </div>
    </main>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "emerald" | "gold" | "bronze";
}) {
  const color =
    accent === "emerald"
      ? "var(--emerald, #006B3F)"
      : accent === "gold"
      ? "var(--gold, #D4AF37)"
      : accent === "bronze"
      ? "var(--bronze, #CD7F32)"
      : "var(--ivory, #FAFAF0)";
  return (
    <div
      style={{
        background: "var(--bg-card, #1A1A2E)",
        border: "1px solid var(--border, #2A2A3E)",
        padding: "14px 16px",
      }}
    >
      <div
        style={{
          fontFamily: "'Josefin Sans', sans-serif",
          fontSize: 9,
          letterSpacing: "0.20em",
          textTransform: "uppercase",
          color: "var(--text-muted-safe, #8B8E96)",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: "'DM Mono', monospace",
          fontSize: 28,
          fontWeight: 700,
          color,
          marginTop: 6,
        }}
      >
        {value}
      </div>
    </div>
  );
}

function Th({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return (
    <th
      style={{
        textAlign: align,
        padding: "10px 14px",
        fontFamily: "'Josefin Sans', sans-serif",
        fontSize: 9,
        letterSpacing: "0.20em",
        textTransform: "uppercase",
        color: "var(--gold-muted, #C5A255)",
        fontWeight: 600,
      }}
    >
      {children}
    </th>
  );
}

function Td({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return (
    <td style={{ padding: "10px 14px", textAlign: align, verticalAlign: "middle" }}>
      {children}
    </td>
  );
}

function VerdictPill({ verdict }: { verdict: string }) {
  const upper = verdict.toUpperCase();
  const isStrong = upper.includes("STRONG");
  const isPass = upper === "PASS";
  const isMarginal = upper.includes("MARGINAL");
  const color = isStrong
    ? "var(--emerald, #006B3F)"
    : isPass
    ? "var(--gold, #D4AF37)"
    : isMarginal
    ? "var(--bronze, #CD7F32)"
    : "var(--ruby, #8B0000)";
  return (
    <span
      style={{
        display: "inline-block",
        padding: "3px 10px",
        border: `1px solid ${color}`,
        color,
        fontFamily: "'Josefin Sans', sans-serif",
        fontSize: 9,
        letterSpacing: "0.18em",
        textTransform: "uppercase",
      }}
    >
      {verdict}
    </span>
  );
}
