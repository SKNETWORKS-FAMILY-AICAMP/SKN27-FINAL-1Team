import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import mascot from '../assets/mascot.png'
import { API_URL } from '../utils/api.js'
import ChatWelcome from './ChatWelcome'
import './FloatingChatbot.css'

const initialSettings = {
  shortAnswer: false,
  fridgeFirst: true,
  expiringFirst: true,
  excludeDislikes: true,
}

const initialMessages = [
  { role: 'bot', text: '무엇을 도와드릴까요? 요리에 관한 모든 것을 물어보세요.' },
]

// 응답 안의 '재료명' 표기를 작은 강조 배지로 바꿔 보여줍니다.
function MessageText({ text }) {
  return (
    <p>
      {String(text).split(/'([^']+)'/g).map((part, index) =>
        index % 2 ? (
          <span className="floating-chatbot__ingredient" key={`${part}-${index}`}>
            {part}
          </span>
        ) : (
          part
        ),
      )}
    </p>
  )
}
// 봇 메시지를 한 글자씩 타이핑하듯 보여주는 애니메이션 컴포넌트입니다.
function TypewriterMessage({ text, onTyping, onComplete }) {
  const [displayedText, setDisplayedText] = useState('')
  const onTypingRef = useRef(onTyping)
  const onCompleteRef = useRef(onComplete)

  // 부모가 다시 렌더링되어도 진행 중인 타이핑 interval은 다시 시작하지 않고 최신 콜백만 참조합니다.
  useEffect(() => {
    onTypingRef.current = onTyping
    onCompleteRef.current = onComplete
  }, [onTyping, onComplete])

  useEffect(() => {
    setDisplayedText('')
    let index = 0
    const interval = setInterval(() => {
      setDisplayedText(text.slice(0, index + 1))
      index += 1
      if (index >= text.length) {
        clearInterval(interval)
        onCompleteRef.current?.()
      }
    }, 30)

    return () => clearInterval(interval)
  }, [text])

  useEffect(() => {
    onTypingRef.current?.()
  }, [displayedText])

  return <MessageText text={displayedText} />
}

function FloatingChatbot() {
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState(initialMessages)
  const [isSending, setIsSending] = useState(false)
  const messagesEndRef = useRef(null)

  // 새 메시지나 로딩 말풍선이 추가되면 마지막 응답으로 이동합니다.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, isSending, isOpen])

  // 확인 버튼은 내부 명령을 보내되 사용자에게는 버튼 라벨만 보여줍니다.
  const requestChat = async (text, displayText = text) => {
    const trimmed = text.trim()
    const visibleText = displayText.trim()
    if (!trimmed || isSending) return

    setMessages((prev) => [...prev, { role: 'user', text: visibleText }])
    setMessage('')
    setIsSending(true)

    try {
      const token = localStorage.getItem('bobbeori-token')
      const headers = { 'Content-Type': 'application/json' }
      // 비회원 챗봇 요청은 Authorization 헤더 없이 보내 게스트로 처리합니다.
      if (token && token !== 'null' && token !== 'undefined') {
        headers.Authorization = `Bearer ${token}`
      }
      // 입력 메시지를 백엔드 챗봇 라우터로 전달합니다.
      const response = await fetch(`${API_URL}/api/v1/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          message: trimmed,
          history: messages.filter((item) => !item.isTyping).map((item) => ({ role: item.role, text: item.text })),
          settings: initialSettings,
        }),
      })

      if (response.status === 401) throw new Error('unauthorized')
      if (!response.ok) throw new Error('chat request failed')

      const data = await response.json()
      // 냉장고 쓰기 작업이 끝난 응답이면 현재 화면의 목록을 새로고침합니다.
      if ((data.actions || []).some((action) => action.data?.refreshInventory)) {
        window.dispatchEvent(new CustomEvent('bobbeori:inventory-updated'))
      }
      setMessages((prev) => [
        ...prev,
        { role: 'bot', text: data.reply, actions: data.actions || [], sources: data.sources || [], isTyping: true },
      ])
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'bot',
          isTyping: true,
          text:
            error.message === 'unauthorized'
              ? '로그인 토큰이 만료되었어요. 다시 로그인한 뒤 이용해주세요.'
              : '챗봇 연결 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.',
        },
      ])
    } finally {
      setIsSending(false)
    }
  }

  const sendMessage = (event) => {
    event.preventDefault()
    requestChat(message)
  }

  return (
    <aside className="floating-chatbot" aria-label="밥벌이 챗봇">
      {isOpen && (
        <section className="floating-chatbot__panel">
          <header className="floating-chatbot__header">
            <div className="floating-chatbot__profile">
              <img src={mascot} alt="" />
              <div>
                <strong>냉장고 도우미 챗봇</strong>
                <span>
                  <i aria-hidden="true" />
                  온라인
                </span>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <button
                type="button"
                aria-label="새 채팅"
                title="새 채팅 시작"
                onClick={() => setMessages(initialMessages)}
                style={{ 
                  width: 'auto',
                  height: 'auto',
                  fontSize: '0.8rem', 
                  padding: '6px 12px', 
                  borderRadius: '16px', 
                  border: '1px solid #e0e0e0', 
                  backgroundColor: '#ffffff',
                  color: '#555',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  cursor: 'pointer',
                  lineHeight: '1'
                }}
              >
                <span style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>+</span> 새 채팅
              </button>
              <button type="button" aria-label="챗봇 닫기" onClick={() => setIsOpen(false)} style={{ fontSize: '1.4rem' }}>
                ×
              </button>
            </div>
          </header>

          <div className="floating-chatbot__messages">
            {messages.map((item, index) => (
              <div className={`floating-chatbot__message-row is-${item.role}`} key={`${item.role}-${index}`}>
                {item.role === 'bot' ? <img className="floating-chatbot__bot-avatar" src={mascot} alt="" /> : null}
                <div className={`floating-chatbot__message is-${item.role}`}>
                  {item.role === 'bot' ? (
                    item.isTyping ? (
                      <TypewriterMessage
                        text={item.text}
                        onTyping={() => messagesEndRef.current?.scrollIntoView({ block: 'end' })}
                        onComplete={() => {
                          setMessages((prev) => {
                            const next = [...prev]
                            next[index] = { ...next[index], isTyping: false }
                            return next
                          })
                        }}
                      />
                    ) : (
                      <MessageText text={item.text} />
                    )
                  ) : (
                    <p>{item.text}</p>
                  )}
                  {item.actions?.some((action) => !action.data?.refreshInventory) ? (
                    <div className="floating-chatbot__actions">
                      {item.actions.filter((action) => !action.data?.refreshInventory).map((action, actionIndex) => (
                        <button
                          type="button"
                          key={`${action.label}-${actionIndex}`}
                          disabled={item.actionDisabled}
                          onClick={() => {
                            // 사용자가 액션 버튼을 클릭하면 해당 그룹의 버튼들을 모두 비활성화
                            setMessages((prev) => {
                              const next = [...prev]
                              next[index] = { ...next[index], actionDisabled: true }
                              return next
                            })
                            // 챗봇 액션은 메시지 전송, 냉장고 갱신, 페이지 이동 중 하나로 처리합니다.
                            if (action.data?.message) {
                              requestChat(action.data.message, action.label)
                              return
                            }
                            if (action.data?.refreshInventory) {
                              window.dispatchEvent(new CustomEvent('bobbeori:inventory-updated'))
                              return
                            }
                            if (action.url) navigate(action.url)
                          }}
                        >
                          {action.label}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {item.sources?.length ? (
                    <div className="floating-chatbot__sources">
                      출처
                      {item.sources.map((source) => (
                        <a key={source.url} href={source.url} target="_blank" rel="noreferrer">
                          {source.title}
                        </a>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
            {isSending ? (
              <div className="floating-chatbot__message-row is-bot">
                <img className="floating-chatbot__bot-avatar" src={mascot} alt="" />
                <div className="floating-chatbot__message is-bot">
                  <div className="floating-chatbot__typing" aria-label="챗봇 응답 작성 중">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </div>
            ) : null}
            {messages.length === 1 && !isSending ? (
              <ChatWelcome onRequestChat={requestChat} />
            ) : null}
            <div ref={messagesEndRef} />
          </div>

          <form className="floating-chatbot__form" onSubmit={sendMessage}>
            <input
              type="text"
              value={message}
              placeholder="메시지를 입력하세요..."
              onChange={(event) => setMessage(event.target.value)}
            />
            <button type="submit" aria-label="메시지 전송">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M4 12.5 19.5 5 16 20l-4.2-6.1L4 12.5Z" />
                <path d="m11.8 13.9 3.9-4.2" />
              </svg>
            </button>
          </form>
        </section>
      )}

      <button
        className="floating-chatbot__toggle"
        type="button"
        aria-label={isOpen ? '챗봇 닫기' : '챗봇 열기'}
        onClick={() => setIsOpen((prev) => !prev)}
      >
        <img src={mascot} alt="" />
      </button>
    </aside>
  )
}

export default FloatingChatbot
