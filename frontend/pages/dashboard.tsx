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

  const handleActionSuccess = (emailId: string) => {
    if (!data) return
    // Optimistic update: filter out the processed email immediately
    const updatedEmails = data.priorityEmails.filter(e => e.id !== emailId)
    // Update local cache without re-fetching yet
    mutate({ ...data, priorityEmails: updatedEmails }, false)
    // Then trigger a real re-fetch to sync with backend and update analytics
    mutate()
  }

  return (
    <div className="min-h-screen bg-slate-900 relative overflow-hidden text-slate-100">
      {/* Dynamic Background Gradients */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-600 rounded-full mix-blend-multiply filter blur-[100px] opacity-40 animate-blob"></div>
      <div className="absolute top-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-600 rounded-full mix-blend-multiply filter blur-[100px] opacity-40 animate-blob animation-delay-2000"></div>
      <div className="absolute bottom-[-10%] left-[20%] w-[40%] h-[40%] bg-teal-600 rounded-full mix-blend-multiply filter blur-[100px] opacity-40 animate-blob animation-delay-4000"></div>

      <div className="relative z-10">
        <Navbar />

        <main className="max-w-7xl mx-auto px-4 py-8">
          <div className="flex items-center justify-between mb-8">
            <h1 className="text-3xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-400">
              Dashboard
            </h1>

            {/* Follow-up count badge */}
            {data && data.followupCount > 0 && (
              <span className="inline-flex items-center gap-2 bg-white/10 backdrop-blur-md text-orange-300 text-sm font-semibold px-4 py-1.5 rounded-full border border-orange-500/30 shadow-[0_0_15px_rgba(249,115,22,0.2)]">
                <span className="w-2.5 h-2.5 rounded-full bg-orange-400 animate-pulse" aria-hidden="true" />
                {data.followupCount} pending follow-up{data.followupCount !== 1 ? 's' : ''}
              </span>
            )}
          </div>

          <div className="grid grid-cols-12 gap-8">
            {/* Priority emails — col-span-8 */}
            <section className="col-span-12 lg:col-span-8 space-y-4" aria-label="Priority emails">
              <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest">
                Priority Inbox
              </h2>

              {isLoading ? (
                <>
                  <SkeletonCard />
                  <SkeletonCard />
                  <SkeletonCard />
                </>
              ) : data?.priorityEmails.length ? (
                <div className="space-y-4">
                  {data.priorityEmails.map((email) => (
                    <div key={email.id} className="transform transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl">
                      <EmailCard email={email} onReplyGenerated={() => handleActionSuccess(email.id)} />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="bg-white/5 backdrop-blur-lg border border-white/10 rounded-2xl p-8 text-center">
                  <p className="text-slate-400 italic">Inbox zero achieved. No priority emails right now.</p>
                </div>
              )}

              {/* Suggested actions */}
              {data?.suggestedActions && data.suggestedActions.length > 0 && (
                <div className="mt-8">
                  <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">
                    Suggested AI Actions
                  </h2>
                  <ul className="space-y-2">
                    {data.suggestedActions.map((action, i) => (
                      <li key={i} className="text-sm text-slate-200 bg-white/5 backdrop-blur-md border border-white/10 rounded-xl px-4 py-3 flex items-center gap-3 transition-colors hover:bg-white/10 cursor-pointer">
                        <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                        {action}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>

            {/* Right column — col-span-4 */}
            <aside className="col-span-12 lg:col-span-4 space-y-8" aria-label="Analytics and brief">
              {/* Analytics widget */}
              <section aria-label="Analytics">
                <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">
                  This Week's Impact
                </h2>
                {isLoading ? (
                  <div className="animate-pulse space-y-3">
                    {[...Array(3)].map((_, i) => (
                      <div key={i} className="h-20 bg-white/5 rounded-2xl backdrop-blur-md border border-white/10" />
                    ))}
                  </div>
                ) : data?.analytics ? (
                  <div className="bg-white/5 backdrop-blur-lg border border-white/10 rounded-2xl p-1 shadow-xl">
                    <AnalyticsWidget stats={data.analytics} />
                  </div>
                ) : null}
              </section>

              {/* Daily brief */}
              <section aria-label="Daily brief">
                <div className="bg-gradient-to-b from-white/10 to-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-1 shadow-2xl relative overflow-hidden group">
                  <div className="absolute inset-0 bg-gradient-to-r from-blue-500/10 via-purple-500/10 to-teal-500/10 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
                  <DailyBriefPanel />
                </div>
              </section>
            </aside>
          </div>
        </main>
      </div>
    </div>
  )
}
