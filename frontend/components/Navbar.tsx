/**
 * Navbar — top navigation bar with links and user session info.
 * Requirements: 2.1
 */

import Link from 'next/link'
import { useRouter } from 'next/router'
import { signOut, useSession } from 'next-auth/react'
import Image from 'next/image'

const NAV_LINKS = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/emails', label: 'Emails' },
  { href: '/calendar', label: 'Calendar' },
  { href: '/analytics', label: 'Analytics' },
]

export default function Navbar() {
  const { data: session } = useSession()
  const router = useRouter()

  return (
    <nav className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between shadow-sm">
      {/* Brand */}
      <div className="flex items-center gap-8">
        <Link href="/dashboard" className="text-lg font-bold text-blue-600 tracking-tight">
          Clone Yourself
        </Link>

        {/* Nav links */}
        <div className="hidden md:flex items-center gap-1">
          {NAV_LINKS.map(({ href, label }) => {
            const isActive = router.pathname === href
            return (
              <Link
                key={href}
                href={href}
                className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                }`}
                aria-current={isActive ? 'page' : undefined}
              >
                {label}
              </Link>
            )
          })}
        </div>
      </div>

      {/* User section */}
      {session?.user && (
        <div className="flex items-center gap-3">
          {/* Avatar */}
          {session.user.image ? (
            <Image
              src={session.user.image}
              alt={session.user.name ?? 'User avatar'}
              width={32}
              height={32}
              className="rounded-full"
            />
          ) : (
            <div
              className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-white text-sm font-semibold"
              aria-hidden="true"
            >
              {session.user.name?.[0]?.toUpperCase() ?? 'U'}
            </div>
          )}

          {/* Name */}
          <span className="hidden sm:block text-sm text-gray-700 font-medium">
            {session.user.name}
          </span>

          {/* Sign out */}
          <button
            onClick={() => signOut({ callbackUrl: '/' })}
            className="text-sm text-gray-500 hover:text-red-600 transition-colors px-2 py-1 rounded"
            aria-label="Sign out"
          >
            Sign out
          </button>
        </div>
      )}
    </nav>
  )
}
