import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "海外销售情报工作台 | Schneider Electric",
  description: "面向施耐德电气销售与 KA 团队的全球项目、招采与客户情报工作台。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
