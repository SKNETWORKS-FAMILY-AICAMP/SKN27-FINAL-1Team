import React, { useEffect, useRef, useState } from 'react'
import './AppDialog.css'

function AppDialog({ dialog, onCancel, onConfirm }) {
  const [inputValue, setInputValue] = useState('')
  const inputRef = useRef(null)

  useEffect(() => {
    if (!dialog) {
      return
    }

    setInputValue(dialog.defaultValue ?? '')

    if (dialog.type === 'prompt') {
      window.setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [dialog])

  // 일반 알림/확인 모달에서도 Enter로 확인합니다.
  useEffect(() => {
    if (!dialog || dialog.type === 'prompt') return

    const handleKeyDown = (event) => {
      if (event.key !== 'Enter') return
      event.preventDefault()
      onConfirm(true)
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [dialog, onConfirm])
  if (!dialog) {
    return null
  }

  const isPrompt = dialog.type === 'prompt'
  const isConfirm = dialog.type === 'confirm'
  const dialogTypeLabel = isPrompt ? '입력' : isConfirm ? null : '알림'

  const handleConfirm = () => {
    onConfirm(isPrompt ? inputValue : true)
  }

  return (
    <div className="app-dialog-overlay" role="presentation" onMouseDown={onCancel}>
      <section
        className={`app-dialog-card${isConfirm ? ' is-confirm' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="app-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="app-dialog-card__header">
          {dialogTypeLabel ? <span>{dialogTypeLabel}</span> : null}
          <button type="button" aria-label="닫기" onClick={onCancel}>
            x
          </button>
        </div>

        <h2 id="app-dialog-title">{dialog.title}</h2>
        <p>{dialog.message}</p>

        {isPrompt ? (
          <input
            ref={inputRef}
            value={inputValue}
            placeholder={dialog.placeholder}
            onChange={(event) => setInputValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                handleConfirm()
              }
            }}
          />
        ) : null}

        <div className="app-dialog-card__actions">
          {isConfirm || isPrompt ? (
            <button className="app-dialog-card__secondary" type="button" onClick={onCancel}>
              {dialog.cancelText ?? '취소'}
            </button>
          ) : null}
          <button className="app-dialog-card__primary" type="button" onClick={handleConfirm}>
            {dialog.confirmText ?? '확인'}
          </button>
        </div>
      </section>
    </div>
  )
}

export function useAppDialog() {
  const [dialog, setDialog] = useState(null)
  const resolverRef = useRef(null)

  const closeDialog = (value) => {
    resolverRef.current?.(value)
    resolverRef.current = null
    setDialog(null)
  }

  const openDialog = (nextDialog) =>
    new Promise((resolve) => {
      resolverRef.current = resolve
      setDialog(nextDialog)
    })

  const showAlert = (message, options = {}) =>
    openDialog({
      type: 'alert',
      title: options.title ?? '알림',
      message,
      confirmText: options.confirmText ?? '확인',
    })

  const showConfirm = (message, options = {}) =>
    openDialog({
      type: 'confirm',
      title: options.title ?? '확인',
      message,
      confirmText: options.confirmText ?? '확인',
      cancelText: options.cancelText ?? '취소',
    })

  const showPrompt = (message, options = {}) =>
    openDialog({
      type: 'prompt',
      title: options.title ?? '입력',
      message,
      placeholder: options.placeholder,
      defaultValue: options.defaultValue ?? '',
      confirmText: options.confirmText ?? '확인',
      cancelText: options.cancelText ?? '취소',
    })

  const dialogNode = (
    <AppDialog
      dialog={dialog}
      onCancel={() => closeDialog(dialog?.type === 'alert' ? true : null)}
      onConfirm={(value) => closeDialog(value)}
    />
  )

  return { dialogNode, showAlert, showConfirm, showPrompt }
}
