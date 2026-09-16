import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "F1 Strategy Agents",
  description: "Multi-agent F1 race strategy demo: strategists and drivers changing each other's decisions",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="h-full">{children}</body>
    </html>
  );
}
