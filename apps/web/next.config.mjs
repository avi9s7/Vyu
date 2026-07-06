/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  experimental: {
    typedRoutes: true,
    instrumentationHook: true
  }
};

export default nextConfig;
