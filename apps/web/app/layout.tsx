import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vyu Evidence Workspace",
  description: "Governed evidence intelligence workspace for Vyu."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
