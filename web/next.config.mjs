/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    // In dev, proxy /api to the backend running on :8000
    if (process.env.NODE_ENV !== "production") {
      return [{ source: "/api/:path*", destination: "http://localhost:8000/:path*" }];
    }
    return [];
  },
};

export default nextConfig;
