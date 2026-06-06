/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Allow next/image to serve from the local public directory
  images: {
    unoptimized: true,   // serve PNG logos as-is (no CDN needed for campus LAN)
  },

  async headers() {
    return [
      {
        source: "/css/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
      {
        source: "/img/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
    ];
  },

  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;