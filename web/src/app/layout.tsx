import "./globals.css";
import type { Metadata } from "next";
import { Navbar } from "@/components/Navbar";
import { SessionIntake } from "@/components/SessionIntake";

export const metadata: Metadata = {
  title: {
    default: "health-mdt · cardiometabolic MDT",
    template: "%s · health-mdt",
  },
  description: "Персональный мультиагентный health-ассистент — 9 специалистов и GP под одной крышей.",
  // Next.js auto-picks /app/icon.svg for favicon + standard <link> tags
  themeColor: "#0a0a0b",
  viewport: "width=device-width, initial-scale=1, maximum-scale=1",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body className="min-h-screen bg-bg text-fg font-sans">
        <SessionIntake />
        <Navbar />
        <main className="mx-auto max-w-6xl px-4 pb-16 pt-4 md:px-6">{children}</main>
      </body>
    </html>
  );
}
