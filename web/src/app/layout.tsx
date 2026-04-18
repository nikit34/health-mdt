import "./globals.css";
import type { Metadata } from "next";
import { Navbar } from "@/components/Navbar";
import { SessionIntake } from "@/components/SessionIntake";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://health.firstmessage.ru";
const DESCRIPTION =
  "Загрузи анализы и данные носимых устройств — команда из 9 ИИ-специалистов и GP прочитает их вместе и выдаст отчёт с 3 конкретными действиями.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Consilium · cardiometabolic MDT",
    template: "%s · Consilium",
  },
  description: DESCRIPTION,
  // Next.js auto-picks /app/icon.svg for favicon + standard <link> tags
  themeColor: "#0a0a0b",
  viewport: "width=device-width, initial-scale=1, maximum-scale=1",
  openGraph: {
    type: "website",
    locale: "ru_RU",
    url: SITE_URL,
    siteName: "Consilium",
    title: "Consilium · cardiometabolic MDT",
    description: DESCRIPTION,
    // og-image is generated at build time by app/opengraph-image.tsx
  },
  twitter: {
    card: "summary_large_image",
    title: "Consilium · cardiometabolic MDT",
    description: DESCRIPTION,
  },
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
