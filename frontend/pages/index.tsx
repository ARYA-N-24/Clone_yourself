/**
 * Root page — redirects authenticated users to /dashboard,
 * unauthenticated users to Google sign-in.
 * Requirements: 1.1
 */

import { GetServerSideProps } from 'next'
import { getServerSession } from 'next-auth/next'
import { signIn } from 'next-auth/react'
import { authOptions } from './api/auth/[...nextauth]'
import { useEffect } from 'react'

export const getServerSideProps: GetServerSideProps = async (context) => {
  const session = await getServerSession(context.req, context.res, authOptions)

  if (session) {
    return {
      redirect: { destination: '/dashboard', permanent: false },
    }
  }

  return { props: {} }
}

export default function Home() {
  // Trigger Google sign-in automatically for unauthenticated users
  useEffect(() => {
    signIn('google', { callbackUrl: '/dashboard' })
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center space-y-4">
        <h1 className="text-2xl font-bold text-gray-900">Clone Yourself</h1>
        <p className="text-gray-500">Redirecting to sign in…</p>
        <div className="flex justify-center">
          <svg className="animate-spin h-6 w-6 text-blue-500" viewBox="0 0 24 24" fill="none" aria-label="Loading">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
        </div>
      </div>
    </div>
  )
}
