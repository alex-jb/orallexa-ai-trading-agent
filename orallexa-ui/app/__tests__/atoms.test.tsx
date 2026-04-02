import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Heading, Row, Toggle, CopyBtn } from "../components/atoms";

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
