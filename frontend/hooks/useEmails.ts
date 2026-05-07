/**
 * useEmails — SWR hook for the email list.
 * Requirements: 3.1
 */

import useSWR from 'swr'
import type { Email } from '@/types'
import { getEmails } from '@/services/api'

export function useEmails() {
  const { data, error, isLoading, mutate } = useSWR<Email[]>(
    '/emails',
    getEmails,
    { revalidateOnFocus: false },
  )

  return {
    emails: data ?? [],
    isLoading,
    error,
    mutate,
  }
}
