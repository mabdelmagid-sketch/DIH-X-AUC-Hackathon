import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  transpilePackages: ["@pos/ui", "@pos/db"],
  // TODO: Remove once proper Supabase types are generated
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default withNextIntl(nextConfig);
