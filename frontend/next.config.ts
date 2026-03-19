import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        // Forward all /api/* to the backend EXCEPT /api/auth/* (Auth.js)
        source: "/api/((?!auth/).*)",
        destination: `${process.env["API_URL"] ?? "http://api:8000"}/:path*`,
      },
    ];
  },
};

export default nextConfig;
