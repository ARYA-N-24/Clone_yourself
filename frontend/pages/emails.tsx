/**
 * Emails page — full email list with filtering by classification.
 * Requirements: 3.1, 4.1
 */

import { useState } from 'react'
import { GetServerSideProps } from 'next'
import { getServerSession } from 'next-auth/next'
import { authOptions } from './api/auth/[...nextauth]'
import Navbar from '@/components/Navbar'
import EmailCard from '@/components/EmailCard'
import { useEmails } from '@/hooks/useEmails'
import type { EmailClassification } from '@/types'

export const getServerSideProps: GetServerSideProps = async (context) => {
  const session = await getServerSession(context.req, context.res, authOptions)
  if (!session) {
    return { redirect: { destination: '/', permanent: false } }
  }
  return { props: {} }
}

const FILTER_OPTIONS: Array<{ value: EmailClassification | 'all'; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'urgent', label: 'Urgent' },
  { value: 'normal', label: 'Normal' },
  { value: 'low', label: 'Low' },
]

export default function EmailsPage() {
  const { emails, isLoading, mutate } = useEmails()
  const [filter, setFilter] = useState<EmailClassification | 'all'>('all')

  const filteredEmails =
    filter === 'all'
      ? emails
      : emails.filter((e) => e.classification === filter)

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />

      <main className="max-w-5xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-bold text-gray-900">Emails</h1>

          {/* Classification filter */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500">Filter:</span>
            <div className="flex gap-1">
              {FILTER_OPTIONS.map(({ value, label }) => (
                <button
                  key={value}
                  onClick={() => setFilter(value)}
                  className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
                    filter === value
                      ? 'bg-blue-600 text-white'
                      : 'bg-white text-gray-600 border border-gray-300 hover:bg-gray-50'
                  }`}
                  aria-pressed={filter === value}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Email list */}
        <div className="space-y-3">
          {isLoading ? (
            <>
              {[...Array(5)].map((_, i) => (
                <div
                  key={i}
                  className="animate-pulse bg-white rounded-lg border border-gray-200 p-4 space-y-2"
                >
                  <div className="h-4 bg-gray-200 rounded w-3/4" />
                  <div className="h-3 bg-gray-200 rounded w-1/2" />
                </div>
              ))}
            </>
          ) : filteredEmails.length > 0 ? (
            filteredEmails.map((email) => (
              <EmailCard key={email.id} email={email} onReplyGenerated={mutate} />
            ))
          ) : (
            <p className="text-sm text-gray-400 italic text-center py-8">
              No emails match the selected filter.
            </p>
          )}
        </div>
      </main>
    </div>
  )
}
