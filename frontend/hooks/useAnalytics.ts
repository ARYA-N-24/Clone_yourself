/**
 * useAnalytics — SWR hook for analytics stats.
 * Requirements: 11.4
 */

import useSWR from 'swr'
import type { AnalyticsStats, DailyMetrics } from '@/types'
import { getAnalyticsStats, getDailyMetrics } from '@/services/api'

export function useAnalytics(period: 'week' | 'month' = 'week') {
  const { data, error, isLoading } = useSWR<AnalyticsStats>(
    `/analytics/stats?period=${period}`,
    () => getAnalyticsStats(period),
    { revalidateOnFocus: false },
  )

  return { stats: data ?? null, isLoading, error }
}

export function useDailyMetrics(period: 'week' | 'month' = 'week') {
  const { data, error, isLoading } = useSWR<DailyMetrics[]>(
    `/analytics/daily?period=${period}`,
    () => getDailyMetrics(period),
    { revalidateOnFocus: false },
  )

  return { dailyData: data ?? [], isLoading, error }
}
