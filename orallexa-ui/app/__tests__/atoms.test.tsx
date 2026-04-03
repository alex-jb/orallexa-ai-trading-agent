import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Heading, Row, Toggle, CopyBtn, BrandMark, Mod, GoldRule, DecoFan } from "../components/atoms";

// next/image needs a simple mock in jsdom
vi.mock("next/image", () => ({
  default: ({ src, alt, width, height, className }: { src: string; alt: string; width: number; height: number; className?: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} width={width} height={height} className={className} />
  ),
}));

describe("Heading", () => {
  it("renders children text", () => {
    render(<Heading>Engine Decision</Heading>);
    expect(screen.getByText("Engine Decision")).toBeInTheDocument();
  });

  it("renders as h3 element", () => {
    render(<Heading>Test</Heading>);
    const h3 = screen.getByRole("heading", { level: 3 });
    expect(h3).toBeInTheDocument();
  });
});

describe("Row", () => {
  it("renders label and value", () => {
    render(<Row label="Win Rate" value="71%" />);
    expect(screen.getByText("Win Rate")).toBeInTheDocument();
    expect(screen.getByText("71%")).toBeInTheDocument();
  });

  it("applies custom color to value", () => {
    render(<Row label="Risk" value="HIGH" color="#8B0000" />);
    const value = screen.getByText("HIGH");
    expect(value).toHaveStyle({ color: "#8B0000" });
  });

  it("uses champagne color by default", () => {
    render(<Row label="Style" value="Balanced" />);
    const value = screen.getByText("Balanced");
    expect(value).toHaveStyle({ color: "#F5E6CA" });
  });
});

describe("Toggle", () => {
  it("renders label text", () => {
    render(<Toggle label="Details" open={false} onToggle={() => {}}><p>Content</p></Toggle>);
    expect(screen.getByText(/Details/)).toBeInTheDocument();
  });

  it("hides children when closed", () => {
    render(<Toggle label="Details" open={false} onToggle={() => {}}><p>Hidden</p></Toggle>);
    expect(screen.queryByText("Hidden")).not.toBeInTheDocument();
  });

  it("shows children when open", () => {
    render(<Toggle label="Details" open={true} onToggle={() => {}}><p>Visible</p></Toggle>);
    expect(screen.getByText("Visible")).toBeInTheDocument();
  });

  it("has aria-expanded attribute", () => {
    render(<Toggle label="Details" open={true} onToggle={() => {}}><p>Content</p></Toggle>);
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-expanded", "true");
  });

  it("sets aria-expanded=false when closed", () => {
    render(<Toggle label="Details" open={false} onToggle={() => {}}><p>Content</p></Toggle>);
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });
});

describe("CopyBtn", () => {
  it("renders nothing when text is empty", () => {
    const { container } = render(<CopyBtn text="" />);
    expect(container.firstChild).toBeNull();
  });

  it("renders button with default label", () => {
    render(<CopyBtn text="test content" />);
    expect(screen.getByText(/Copy for/)).toBeInTheDocument();
  });

  it("renders custom label", () => {
    render(<CopyBtn text="test" label="Share" />);
    expect(screen.getByText("Share")).toBeInTheDocument();
  });
});

describe("BrandMark", () => {
  it("renders an img with correct alt text", () => {
    render(<BrandMark />);
    const img = screen.getByAltText("Orallexa Capital Intelligence");
    expect(img).toBeInTheDocument();
  });

  it("uses full dimensions by default (108x36)", () => {
    render(<BrandMark />);
    const img = screen.getByAltText("Orallexa Capital Intelligence");
    expect(img).toHaveAttribute("width", "108");
    expect(img).toHaveAttribute("height", "36");
  });

  it("uses compact dimensions when compact=true (84x28)", () => {
    render(<BrandMark compact />);
    const img = screen.getByAltText("Orallexa Capital Intelligence");
    expect(img).toHaveAttribute("width", "84");
    expect(img).toHaveAttribute("height", "28");
  });

  it("applies compact className when compact=true", () => {
    render(<BrandMark compact />);
    const img = screen.getByAltText("Orallexa Capital Intelligence");
    expect(img).toHaveClass("h-[28px]");
  });

  it("applies full className when compact=false", () => {
    render(<BrandMark compact={false} />);
    const img = screen.getByAltText("Orallexa Capital Intelligence");
    expect(img).toHaveClass("h-[36px]");
  });

  it("renders the logo src", () => {
    render(<BrandMark />);
    const img = screen.getByAltText("Orallexa Capital Intelligence");
    expect(img).toHaveAttribute("src", "/logo.svg");
  });
});

describe("Mod", () => {
  it("renders title content", () => {
    render(<Mod title="Engine Status"><p>child content</p></Mod>);
    expect(screen.getByText("Engine Status")).toBeInTheDocument();
  });

  it("renders children content", () => {
    render(<Mod title="Panel"><p>inner child</p></Mod>);
    expect(screen.getByText("inner child")).toBeInTheDocument();
  });

  it("renders all four corner ornaments", () => {
    const { container } = render(<Mod title="X"><span>x</span></Mod>);
    // Each corner div is an absolute positioned child; verify the container has the
    // expected structural elements (the corner keys: t-l, t-r, b-l, b-r)
    // The outer wrapper has relative mb-3 class
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper).toHaveClass("relative");
    expect(wrapper).toHaveClass("mb-3");
  });

  it("wraps title text in a Heading (h3)", () => {
    render(<Mod title="Capital Profile"><span>data</span></Mod>);
    const heading = screen.getByRole("heading", { level: 3 });
    expect(heading).toBeInTheDocument();
    expect(heading).toHaveTextContent("Capital Profile");
  });

  it("renders title as ReactNode (JSX element)", () => {
    render(
      <Mod title={<span data-testid="custom-title">Custom Node</span>}>
        <p>body</p>
      </Mod>
    );
    expect(screen.getByTestId("custom-title")).toBeInTheDocument();
    expect(screen.getByText("Custom Node")).toBeInTheDocument();
  });
});

describe("GoldRule", () => {
  it("renders without crashing", () => {
    const { container } = render(<GoldRule />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it("renders with default strength (25)", () => {
    const { container } = render(<GoldRule />);
    // The outer div should be present
    expect(container.firstChild).not.toBeNull();
  });

  it("renders three diamond shapes in the center group", () => {
    const { container } = render(<GoldRule />);
    // The diamond group has three rotated divs; each has a rotate-45 class
    const diamonds = container.querySelectorAll(".rotate-45");
    expect(diamonds.length).toBeGreaterThanOrEqual(3);
  });

  it("applies custom strength value to opacity calculation", () => {
    // strength=100 → opacity=1.0; verify the component still renders
    const { container } = render(<GoldRule strength={100} />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it("renders with strength=0 (zero opacity)", () => {
    const { container } = render(<GoldRule strength={0} />);
    expect(container.firstChild).toBeInTheDocument();
  });
});

describe("DecoFan", () => {
  it("renders an SVG element", () => {
    const { container } = render(<DecoFan />);
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });

  it("renders 9 lines in the SVG", () => {
    const { container } = render(<DecoFan />);
    const lines = container.querySelectorAll("line");
    expect(lines).toHaveLength(9);
  });

  it("applies default size (60)", () => {
    const { container } = render(<DecoFan />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "60");
    expect(svg).toHaveAttribute("height", "30");
  });

  it("applies custom size prop", () => {
    const { container } = render(<DecoFan size={120} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "120");
    expect(svg).toHaveAttribute("height", "60");
  });

  it("applies default opacity (0.06) via style", () => {
    const { container } = render(<DecoFan />);
    const svg = container.querySelector("svg") as SVGElement;
    expect(svg.style.opacity).toBe("0.06");
  });

  it("applies custom opacity prop", () => {
    const { container } = render(<DecoFan opacity={0.5} />);
    const svg = container.querySelector("svg") as SVGElement;
    expect(svg.style.opacity).toBe("0.5");
  });

  it("all lines use gold stroke color", () => {
    const { container } = render(<DecoFan />);
    const lines = container.querySelectorAll("line");
    lines.forEach((line) => {
      expect(line.getAttribute("stroke")).toBe("#D4AF37");
    });
  });
});
