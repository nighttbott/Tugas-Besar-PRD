/**
 * app/layout.tsx
 * Root Next.js layout.
 *
 * CSS loading strategy (in globals.css via @import):
 *   1. bootstrap.min.css       → Bootstrap 3.3.7 grid + base components
 *   2. bootstrap-theme.min.css → Bootstrap optional theme
 *   3. roboto.css              → Google Fonts Roboto (the real SIX font file)
 *   4. all.css                 → Font Awesome 5 Free
 *   5. v4-shims.css            → FA v4 compatibility shims
 *   6. bootstrap-notifications.min.css
 *   7. jquery-confirm.min.css
 *
 * Then globals.css applies:
 *   - Verbatim style-20200730.css rules (real SIX overrides)
 *   - Next.js layout fixes (cancel padding-top/margin-bottom for fixed navbar)
 *   - All parking-specific component styles
 *   - Responsive breakpoints
 *
 * No inline <style> blocks anywhere. All CSS is in one cacheable file.
 */
import type { Metadata } from "next";
import Providers from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "ANPR Parking Gate ITB",
  description: "Sistem Parkir Pintar ITB Jatinangor",
};

// Pisahkan viewport ke sini:
export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="id">
      <body>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
