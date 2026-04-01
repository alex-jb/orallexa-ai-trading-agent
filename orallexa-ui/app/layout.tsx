import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Orallexa Capital",
  description: "AI-Powered Capital Intelligence Engine",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased" style={{ background: "#050607" }}>
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Poiret+One&family=Josefin+Sans:wght@300;400;600;700&family=Lato:wght@300;400;700&family=DM+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body
        className="h-full"
        style={{ background: "#08090C", minHeight: "100vh" }}
      >
        {children}
      </body>
    </html>
  );
}
