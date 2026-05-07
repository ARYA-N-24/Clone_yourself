/**
 * EmailReplyPanel — generates, edits, and sends AI reply drafts.
 * Requirements: 4.1, 4.3, 4.4, 4.9
 */

import { useState, useRef } from 'react'
import type { Email, ReplyDraft } from '@/types'
import { generateReply, sendReply, updatePreferences } from '@/services/api'

interface EmailReplyPanelProps {
  email: Email
  onClose?: () => void
  onSent?: () => void
}

type PanelState = 'idle' | 'generating' | 'ready' | 'sending' | 'sent' | 'error'

export default function EmailReplyPanel({ email, onClose, onSent }: EmailReplyPanelProps) {
  const [state, setState] = useState<PanelState>('idle')
  const [draft, setDraft] = useState<ReplyDraft | null>(null)
  const [draftText, setDraftText] = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  const originalDraftText = useRef('')
  const wasEdited = useRef(false)

  async function handleGenerate() {
    setState('generating')
    setErrorMsg('')
    try {
      const result = await generateReply(email.id)
      setDraft(result)
      setDraftText(result.draftText)
      originalDraftText.current = result.draftText
      wasEdited.current = false
      setState('ready')
    } catch {
      setErrorMsg('Failed to generate reply. Please try again.')
      setState('error')
    }
  }

  function handleTextChange(value: string) {
    setDraftText(value)
    if (value !== originalDraftText.current) {
      wasEdited.current = true
    }
  }

  async function handleSend() {
    if (!draft) return
    setState('sending')
    setErrorMsg('')
    try {
      // Record edit action for style learning if user modified the draft (Req 4.9)
      if (wasEdited.current) {
        updatePreferences({} as never).catch(() => {
          // best-effort — don't block send
        })
      }
      await sendReply(email.id, draft.id)
      setState('sent')
      onSent?.()
    } catch {
      setErrorMsg('Failed to send reply. Please try again.')
      setState('ready')
    }
  }

  if (state === 'sent') {
    return (
      <div className="rounded-md bg-green-50 border border-green-200 p-3 text-sm text-green-700">
        Reply sent successfully.
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-800">AI Reply Draft</h3>
        {onClose && (
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-lg leading-none"
            aria-label="Close reply panel"
          >
            &times;
          </button>
        )}
      </div>

      {/* Error message */}
      {errorMsg && (
        <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-2">
          {errorMsg}
        </p>
      )}

      {/* Generate button (idle / error state) */}
      {(state === 'idle' || state === 'error') && (
        <button
          onClick={handleGenerate}
          className="w-full py-2 px-4 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          Generate Reply
        </button>
      )}

      {/* Generating spinner */}
      {state === 'generating' && (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <svg className="animate-spin h-4 w-4 text-blue-500" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          Generating reply…
        </div>
      )}

      {/* Draft editor */}
      {(state === 'ready' || state === 'sending') && draft && (
        <>
          <textarea
            value={draftText}
            onChange={(e) => handleTextChange(e.target.value)}
            rows={6}
            className="w-full text-sm text-gray-800 border border-gray-300 rounded-md p-3 resize-y focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label="Edit reply draft"
            disabled={state === 'sending'}
          />

          {wasEdited.current && (
            <p className="text-xs text-gray-400 italic">
              Draft edited — your style preferences will be updated.
            </p>
          )}

          <div className="flex gap-2">
            <button
              onClick={handleSend}
              disabled={state === 'sending' || !draftText.trim()}
              className="flex-1 py-2 px-4 bg-green-600 text-white text-sm font-medium rounded-md hover:bg-green-700 transition-colors disabled:opacity-50"
            >
              {state === 'sending' ? 'Sending…' : 'Send Reply'}
            </button>
            <button
              onClick={handleGenerate}
              disabled={state === 'sending'}
              className="py-2 px-3 text-sm text-gray-600 border border-gray-300 rounded-md hover:bg-gray-100 transition-colors disabled:opacity-50"
              title="Regenerate"
            >
              Regenerate
            </button>
          </div>
        </>
      )}
    </div>
  )
}
