import type { Metadata } from "next";
import { Providers } from "./providers";

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
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
