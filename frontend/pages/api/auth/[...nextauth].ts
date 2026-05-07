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
     * can be forwarded to the FastAPI backend.
     */
    async jwt({ token, account }) {
      if (account) {
        token.accessToken = account.access_token
        token.refreshToken = account.refresh_token
        token.expiresAt = account.expires_at
      }
      return token
    },

    /**
     * Expose the access token on the session object so the API client can
     * attach it as a Bearer token.
     */
    async session({ session, token }) {
      ;(session as typeof session & { accessToken?: string }).accessToken =
        token.accessToken as string | undefined
      return session
    },
  },

  pages: {
    signIn: '/',
  },

  secret: process.env.NEXTAUTH_SECRET,
}

export default NextAuth(authOptions)
