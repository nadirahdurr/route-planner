import "./globals.css";

import type { Metadata } from "next";
import { ReactNode } from "react";

import { QueryProvider } from "@/components/query-provider";

export const metadata: Metadata = {
  title: "Mission Route Planner",
  description: "Tactical route planning with terrain analysis",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="bg-slate-950">
      <body>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
