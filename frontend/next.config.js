/** @type {import('next').NextConfig} */
const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const nextConfig = {
  reactStrictMode: true,

  images: {
    domains: ['lh3.googleusercontent.com'],
  },

  env: {
    NEXT_PUBLIC_API_URL: apiUrl,
  },

  async rewrites() {
    return [
      {
        source: '/api/backend/:path*',
        destination: `${apiUrl}/:path*`,
      },
    ]
  },
}

module.exports = nextConfig