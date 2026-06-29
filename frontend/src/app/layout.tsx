import type { Metadata } from "next";
import "./globals.css";

import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";

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
    <html lang="en">
      <body className="font-sans antialiased">
        <div className="flex min-h-screen">
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col">
            <Topbar />
            <main className="flex-1 px-6 py-8 md:px-10">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
