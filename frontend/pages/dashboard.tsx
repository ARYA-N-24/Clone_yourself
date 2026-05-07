/**
 * Dashboard page — unified view of priority emails, analytics, daily brief,
 * and follow-up count.
 * Requirements: 2.1, 2.3, 8.1
 */

import { GetServerSideProps } from 'next'
import { getServerSession } from 'next-auth/next'
import { authOptions } from './api/auth/[...nextauth]'
import Navbar from '@/components/Navbar'
import EmailCard from '@/components/EmailCard'
import AnalyticsWidget from '@/components/AnalyticsWidget'
import DailyBriefPanel from '@/components/DailyBriefPanel'
import { useDashboard } from '@/hooks/useDashboard'

// Skeleton loader for cards
function SkeletonCard() {
  return (
    <div className="animate-pulse bg-white rounded-lg border border-gray-200 p-4 space-y-3">
      <div className="h-4 bg-gray-200 rounded w-3/4" />
      <div className="h-3 bg-gray-200 rounded w-1/2" />
      <div className="h-3 bg-gray-200 rounded w-full" />
    </div>
  )
}

export const getServerSideProps: GetServerSideProps = async (context) => {
  const session = await getServerSession(context.req, context.res, authOptions)
  if (!session) {
    return { redirect: { destination: '/', permanent: false } }
  }
  return { props: {} }
}

export default function DashboardPage() {
  const { data, isLoading, mutate } = useDashboard()

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />

      <main className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-bold text-gray-900">Dashboard</h1>

          {/* Follow-up count badge (Req 2.3) */}
          {data && data.followupCount > 0 && (
            <span className="inline-flex items-center gap-1.5 bg-orange-100 text-orange-700 text-sm font-semibold px-3 py-1 rounded-full">
              <span className="w-2 h-2 rounded-full bg-orange-500" aria-hidden="true" />
              {data.followupCount} follow-up{data.followupCount !== 1 ? 's' : ''} pending
            </span>
          )}
        </div>

        <div className="grid grid-cols-12 gap-6">
          {/* Priority emails — col-span-8 */}
          <section className="col-span-12 lg:col-span-8 space-y-3" aria-label="Priority emails">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">
              Priority Emails
            </h2>

            {isLoading ? (
              <>
                <SkeletonCard />
                <SkeletonCard />
                <SkeletonCard />
              </>
            ) : data?.priorityEmails.length ? (
              data.priorityEmails.map((email) => (
                <EmailCard key={email.id} email={email} onReplyGenerated={mutate} />
              ))
            ) : (
              <p className="text-sm text-gray-400 italic">No priority emails right now.</p>
            )}

            {/* Suggested actions */}
            {data?.suggestedActions && data.suggestedActions.length > 0 && (
              <div className="mt-4">
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Suggested Actions
                </h2>
                <ul className="space-y-1">
                  {data.suggestedActions.map((action, i) => (
                    <li key={i} className="text-sm text-gray-700 bg-blue-50 rounded px-3 py-2">
                      {action}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {/* Right column — col-span-4 */}
          <aside className="col-span-12 lg:col-span-4 space-y-6" aria-label="Analytics and brief">
            {/* Analytics widget */}
            <section aria-label="Analytics">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                This Week
              </h2>
              {isLoading ? (
                <div className="animate-pulse space-y-2">
                  {[...Array(3)].map((_, i) => (
                    <div key={i} className="h-16 bg-gray-200 rounded-lg" />
                  ))}
                </div>
              ) : data?.analytics ? (
                <AnalyticsWidget stats={data.analytics} />
              ) : null}
            </section>

            {/* Daily brief */}
            <section aria-label="Daily brief">
              <DailyBriefPanel />
            </section>
          </aside>
        </div>
      </main>
    </div>
  )
}
