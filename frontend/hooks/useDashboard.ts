/**
 * useDashboard — SWR hook for the dashboard payload.
 * Requirements: 2.1, 2.4
 */

import useSWR from 'swr'
import type { DashboardPayload } from '@/types'
import { getDashboard } from '@/services/api'

export function useDashboard() {
  const { data, error, isLoading, mutate } = useSWR<DashboardPayload>(
    '/dashboard',
    getDashboard,
    { revalidateOnFocus: false },
  )

  return { data, isLoading, error, mutate }
}
