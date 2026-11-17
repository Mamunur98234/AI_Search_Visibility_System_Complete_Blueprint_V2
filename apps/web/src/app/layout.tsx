import type { Metadata } from "next";
import { headers } from "next/headers";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "AI Search Visibility", template: "%s · AI Search Visibility" },
  description: "Evidence-based search and AI visibility workspace for agencies.",
  robots: { index: false, follow: false },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Reading request headers opts into dynamic rendering, which the per-request CSP nonce requires.
  await headers();
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
