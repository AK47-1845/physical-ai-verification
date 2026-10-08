import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import "./site.css";
import "./workbench.css";
import "./workspace.css";
import "./demo.css";
import "./free-lab.css";
import "./shared.css";
import "./page-tools.css";
import "./product.css";
import AppShell from "@/components/AppShell";

const geistSans = localFont({
  src: "../../node_modules/@fontsource-variable/geist/files/geist-latin-wght-normal.woff2",
  variable: "--font-geist-sans",
  display: "swap",
});

const geistMono = localFont({
  src: "../../node_modules/@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2",
  variable: "--font-geist-mono",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : 'http://localhost:5190')),
  title: "Verification for Physical AI",
  description: "An evidence-first verification and governance engine for robots and embodied AI. Test behavior, expose failure, and build an auditable case for deployment.",
  openGraph: { title: "Verification for Physical AI", description: "Physical intelligence needs physical evidence.", type: "website", images: [{ url: "/opengraph-image", width: 1200, height: 630 }] },
  twitter: { card: "summary_large_image", title: "Physical AI, verified", images: ["/opengraph-image"] },
  robots: { index: true, follow: true },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body><a href="#main" className="skip-link">Skip to content</a><AppShell>{children}</AppShell></body>
    </html>
  );
}
