import "./globals.css";
import type { Metadata } from "next";
import { Navbar } from "@/components/Navbar";

export const metadata: Metadata = {
  title: "health-mdt",
  description: "Персональный мультиагентный health-ассистент",
  viewport: "width=device-width, initial-scale=1, maximum-scale=1",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body className="min-h-screen bg-bg text-fg font-sans">
        <Navbar />
        <main className="mx-auto max-w-6xl px-4 pb-16 pt-4 md:px-6">{children}</main>
      </body>
    </html>
  );
}
