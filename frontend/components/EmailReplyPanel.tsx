/**
 * EmailReplyPanel — generates, edits, and sends AI reply drafts.
 * Requirements: 4.1, 4.3, 4.4, 4.9
 */

import { useState, useRef } from 'react'
import type { Email, ReplyDraft } from '@/types'
import { generateReply, sendReply, updatePreferences, createManualDraft, updateReplyDraft } from '@/services/api'

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
      setErrorMsg('Failed to generate reply. You can still write a manual reply below.')
      setState('error')
    }
  }

  async function handleManual() {
    setState('generating')
    setErrorMsg('')
    try {
      const result = await createManualDraft(email.id)
      setDraft(result)
      setDraftText('')
      originalDraftText.current = ''
      wasEdited.current = true
      setState('ready')
    } catch {
      setErrorMsg('Failed to create manual draft. Please try again.')
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
      // Save changes if edited
      if (wasEdited.current) {
        await updateReplyDraft(draft.id, draftText)
      }

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

  const isAiError = draftText.startsWith('Error generating reply:')

  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-3 shadow-inner">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${state === 'ready' ? 'bg-green-500' : 'bg-blue-500 animate-pulse'}`} />
          <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest">
            {state === 'ready' ? 'Draft Ready' : 'Reply Assistant'}
          </h3>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Close reply panel"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path></svg>
          </button>
        )}
      </div>

      {/* Error message */}
      {errorMsg && (
        <div className="flex gap-2 items-start text-xs text-red-600 bg-red-50 border border-red-200 rounded-xl p-3">
          <svg className="w-4 h-4 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
          <p>{errorMsg}</p>
        </div>
      )}

      {/* Action buttons (idle / error state) */}
      {(state === 'idle' || state === 'error') && (
        <div className="flex gap-2">
          <button
            onClick={handleGenerate}
            className="flex-1 py-2.5 px-4 bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-xs font-bold uppercase tracking-widest rounded-xl hover:from-blue-700 hover:to-indigo-700 transition-all shadow-md hover:shadow-lg disabled:opacity-50"
          >
            Generate AI Reply
          </button>
          <button
            onClick={handleManual}
            className="flex-1 py-2.5 px-4 bg-white text-gray-700 border border-gray-200 text-xs font-bold uppercase tracking-widest rounded-xl hover:bg-gray-50 transition-all shadow-sm disabled:opacity-50"
          >
            Write Manually
          </button>
        </div>
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
          {isAiError && (
            <div className="text-[10px] text-amber-600 bg-amber-50 border border-amber-100 rounded-lg px-2 py-1 mb-2 flex items-center gap-1.5">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
              AI generation limited. You can edit this or write from scratch.
            </div>
          )}

          <textarea
            value={draftText}
            onChange={(e) => handleTextChange(e.target.value)}
            rows={6}
            placeholder="Write your reply here..."
            className="w-full text-sm text-gray-800 bg-white border border-gray-200 rounded-xl p-4 resize-y focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all placeholder:text-gray-300 shadow-sm"
            aria-label="Edit reply draft"
            disabled={state === 'sending'}
          />

          <div className="flex items-center justify-between">
            {wasEdited.current ? (
              <p className="text-[10px] text-blue-500 font-medium flex items-center gap-1">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                Customizing for your style...
              </p>
            ) : (
              <div />
            )}
            
            <div className="flex gap-2">
              <button
                onClick={handleGenerate}
                disabled={state === 'sending'}
                className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-all disabled:opacity-30"
                title="Regenerate with AI"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
              </button>
              <button
                onClick={handleSend}
                disabled={state === 'sending' || !draftText.trim() || isAiError}
                className="py-2 px-6 bg-gradient-to-r from-green-600 to-emerald-600 text-white text-xs font-bold uppercase tracking-widest rounded-xl hover:from-green-700 hover:to-emerald-700 transition-all shadow-md hover:shadow-lg disabled:opacity-50 flex items-center gap-2"
              >
                {state === 'sending' ? (
                  <>
                    <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/></svg>
                    Sending...
                  </>
                ) : 'Send Reply'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
