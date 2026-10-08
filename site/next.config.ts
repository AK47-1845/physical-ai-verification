import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  devIndicators: false,
  turbopack: { root: path.resolve(__dirname, "..") },
  output: process.env.VERIFICATION_STATIC_EXPORT === "1" ? "export" : undefined,
  distDir: process.env.VERIFICATION_STATIC_EXPORT === "1" ? ".next-transfer" : process.env.NEXT_DIST_DIR ?? ".next",
};

export default nextConfig;
