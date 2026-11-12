import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Панель мониторинга доступности — D4NMS",
  description: "Веб-панель мониторинга доступности сетевых устройств (демо на моках)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
