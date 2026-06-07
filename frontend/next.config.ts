import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  devIndicators: false,
  // The frontend is commonly accessed through Docker port mappings on localhost/127.0.0.1.
  // Next 16 blocks cross-origin dev asset requests unless these origins are explicitly allowed.
  allowedDevOrigins: [
    "localhost",
    "127.0.0.1",
    "[::1]",
    "localhost:3000",
    "127.0.0.1:3000",
    "[::1]:3000",
    "localhost:3001",
    "127.0.0.1:3001",
    "[::1]:3001",
  ],
  // Skip TypeScript errors during builds for now
  typescript: {
    ignoreBuildErrors: false,
  },
};

export default nextConfig;
