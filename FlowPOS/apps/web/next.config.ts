import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@pos/ui", "@pos/db"],
  typescript: {
    ignoreBuildErrors: true,
  },
  async rewrites() {
    const forecastingUrl =
      process.env.FORECASTING_API_URL || "http://localhost:8002";
    return [
      {
        source: "/api/forecast/:path*",
        destination: `${forecastingUrl}/api/:path*`,
      },
    ];
  },
};

export default withNextIntl(nextConfig);
