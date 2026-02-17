import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "KMFlow - Process Intelligence Platform",
  description:
    "AI-powered Process Intelligence platform for consulting engagements",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
          backgroundColor: "#f9fafb",
          color: "#111827",
        }}
      >
        {children}
      </body>
    </html>
  );
}
