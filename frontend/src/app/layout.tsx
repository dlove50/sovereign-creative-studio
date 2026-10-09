import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

import { AssistantPanel } from "@/components/assistant/assistant-panel";
import { AppRail } from "@/components/shell/app-rail";
import { Topbar } from "@/components/topbar";

const sans = Plus_Jakarta_Sans({ subsets: ["latin"], variable: "--font-sans", display: "swap" });

export const metadata: Metadata = {
  title: "Sovereign Creative Studio",
  description: "AI content generation studio — prompt to visuals.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={sans.variable}>
      <body className="font-sans antialiased">
        <div className="flex min-h-screen">
          <AppRail />
          <div className="flex min-w-0 flex-1 flex-col">
            <Topbar />
            <main className="flex-1 px-6 py-8 md:px-10">{children}</main>
          </div>
        </div>
        <AssistantPanel />
      </body>
    </html>
  );
}
