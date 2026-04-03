export default function Loading() {
  return (
    <div
      className="flex min-h-screen items-center justify-center"
      style={{ background: "var(--bg-deep, #0A0A0F)" }}
    >
      <div className="flex flex-col items-center gap-4">
        {/* Gold shimmer spinner */}
        <div
          className="w-8 h-8 border-2 border-t-transparent rounded-full anim-spin"
          style={{ borderColor: "#D4AF37", borderTopColor: "transparent" }}
        />
        <span
          className="text-[10px] font-[Josefin_Sans] uppercase tracking-[0.2em]"
          style={{
            background: "linear-gradient(135deg, #D4AF37, #FFD700, #C5A255)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          Loading Intelligence...
        </span>
      </div>
    </div>
  );
}
