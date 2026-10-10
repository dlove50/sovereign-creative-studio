import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

import { AssistantPanel } from "@/components/assistant/assistant-panel";
import { MotionProvider } from "@/components/motion/motion-provider";
import { ConfirmHost } from "@/components/ui/confirm-host";
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
        <MotionProvider>
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[110] focus:rounded-xl focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary-foreground"
          >
            Skip to content
          </a>
          <div className="flex min-h-screen">
            <AppRail />
            <div className="flex min-w-0 flex-1 flex-col">
              <Topbar />
              <main id="main-content" tabIndex={-1} className="flex-1 px-6 py-8 focus:outline-none md:px-10">{children}</main>
            </div>
          </div>
          <ConfirmHost />
          <AssistantPanel />
        </MotionProvider>
      </body>
    </html>
  );
}
