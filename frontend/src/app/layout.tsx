import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { Providers } from "./providers";
import { SignOutButton } from "@/components/sign-out-button";

export const metadata: Metadata = {
  title: "RBAC MLflow",
  description: "Role-based access control for MLflow",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <nav className="border-b border-gray-200 bg-white px-6 py-3 flex items-center gap-6 text-sm">
            <Link
              href="/dashboard"
              className="text-gray-700 hover:text-blue-600 font-medium"
            >
              Experiments
            </Link>
            <Link
              href="/datasets"
              className="text-gray-700 hover:text-blue-600 font-medium"
            >
              Datasets
            </Link>
            <span className="ml-auto">
              <SignOutButton />
            </span>
          </nav>
          {children}
        </Providers>
      </body>
    </html>
  );
}
