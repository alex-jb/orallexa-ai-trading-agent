import type { Metadata, Viewport } from "next";
import { Poiret_One, Josefin_Sans, Lato, DM_Mono } from "next/font/google";
import "./globals.css";

const poiretOne = Poiret_One({ weight: "400", subsets: ["latin"], variable: "--font-poiret", display: "swap" });
const josefinSans = Josefin_Sans({ weight: ["300", "400", "600", "700"], subsets: ["latin"], variable: "--font-josefin", display: "swap" });
const lato = Lato({ weight: ["300", "400", "700"], subsets: ["latin"], variable: "--font-lato", display: "swap" });
const dmMono = DM_Mono({ weight: ["400", "500"], subsets: ["latin"], variable: "--font-dm-mono", display: "swap" });

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  userScalable: true,
  themeColor: "#0A0A0F",
  colorScheme: "dark",
};

export const metadata: Metadata = {
  title: "Orallexa Capital",
  description: "AI-Powered Capital Intelligence Engine — Multi-agent trading analysis with ML ensemble, news sentiment, and voice coaching.",
  manifest: "/manifest.json",
  icons: {
    icon: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Orallexa",
  },
  openGraph: {
    title: "Orallexa Capital",
    description: "AI-Powered Capital Intelligence Engine",
    siteName: "Orallexa",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Orallexa Capital",
    description: "AI-Powered Capital Intelligence Engine",
    creator: "@orallexatrading",
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`h-full antialiased ${poiretOne.variable} ${josefinSans.variable} ${lato.variable} ${dmMono.variable}`} style={{ background: "#050607" }}>
      <body
        className="h-full"
        style={{ background: "#08090C", minHeight: "100vh" }}
      >
        {children}
      </body>
    </html>
  );
}
