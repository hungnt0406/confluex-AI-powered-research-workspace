import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: __dirname,
  },
  // Next 16 blocks cross-origin dev resources by default. Allow LAN access (e.g.
  // testing the dev server on another device on the same Wi-Fi, or via a Windows
  // Hyper-V / WSL virtual adapter such as 172.18.x.x).
  allowedDevOrigins: ["172.18.64.1", "localhost", "127.0.0.1"],
};
export default nextConfig;
