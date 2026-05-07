/**
 * NextAuth.js configuration — Google OAuth provider.
 * Requests Gmail + Calendar scopes and stores the JWT in the session.
 * Requirements: 1.1, 1.2, 12.6
 */

import NextAuth, { NextAuthOptions } from 'next-auth'
import GoogleProvider from 'next-auth/providers/google'

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      authorization: {
        params: {
          scope: [
            'openid',
            'email',
            'profile',
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/calendar.readonly',
            'https://www.googleapis.com/auth/calendar.events',
          ].join(' '),
          access_type: 'offline',
          prompt: 'consent',
        },
      },
    }),
  ],

  callbacks: {
    /**
     * Persist the Google access token and refresh token in the JWT so they
     * can be forwarded to the FastAPI backend. Also sync them with the backend
     * to obtain a backend-signed JWT.
     */
    async jwt({ token, account, user }) {
      if (account && user) {
        token.accessToken = account.access_token
        token.refreshToken = account.refresh_token
        token.expiresAt = account.expires_at

        // Sync with backend to get a backend-issued JWT
        try {
          const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
          const res = await fetch(`${baseUrl}/auth/nextauth`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              email: user.email,
              name: user.name,
              picture_url: user.image,
              access_token: account.access_token,
              refresh_token: account.refresh_token || '',
              expires_at: account.expires_at,
            })
          });
          if (res.ok) {
            const data = await res.json();
            token.backendJwt = data.access_token;
          } else {
            console.error("Backend sync failed:", await res.text());
          }
        } catch (e) {
          console.error("Failed to sync with backend", e);
        }
      }
      return token
    },

    /**
     * Expose the access token on the session object so the API client can
     * attach it as a Bearer token. We use the backend-issued JWT.
     */
    async session({ session, token }) {
      ;(session as typeof session & { accessToken?: string }).accessToken =
        (token.backendJwt as string | undefined) || (token.accessToken as string | undefined)
      return session
    },
  },

  pages: {
    signIn: '/',
  },

  secret: process.env.NEXTAUTH_SECRET,
}

export default NextAuth(authOptions)
