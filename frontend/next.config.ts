import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return {
      beforeFiles: [],
      afterFiles: [],
      fallback: [
        {
          // Runs after all filesystem routes (incl. [...nextauth] dynamic route)
          source: "/api/:path*",
          destination: `${process.env["API_URL"] ?? "http://api:8000"}/:path*`,
        },
      ],
    };
  },
};

export default nextConfig;
