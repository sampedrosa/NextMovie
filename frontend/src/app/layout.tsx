import type { Metadata } from "next";
import { DM_Sans, Playfair_Display } from "next/font/google";
import "./globals.css";

const dmSans = DM_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-dm-sans",
  weight: ["400", "500", "700"],
});

const playfair = Playfair_Display({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-playfair",
  weight: ["500", "700"],
});

export const metadata: Metadata = {
  title: "NextMovie — descubra seu próximo filme",
  description:
    "Descreva o filme que você quer assistir e receba recomendações por busca semântica, além do óbvio.",
  icons: { icon: "/nextmovie-logo.png" },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" className={`${dmSans.variable} ${playfair.variable}`}>
      <body className="antialiased">{children}</body>
    </html>
  );
}
