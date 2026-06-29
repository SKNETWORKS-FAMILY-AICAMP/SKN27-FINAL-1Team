import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import mascot from '../assets/mascot.png'
import './FloatingChatbot.css'

const initialSettings = {
  shortAnswer: true,
  fridgeFirst: true,
  expiringFirst: true,
  lowMissing: true,
  excludeDislikes: true,
}

const initialMessages = [
  { role: 'bot', text: '안녕하세요. 레시피, 보관법, 장보기를 도와드릴게요.' },
]

const quickQuestions = ['냉장고 요약해줘', '임박 재료 알려줘', '오늘 뭐 먹을까?']

function FloatingChatbot() {
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('home')
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState(initialMessages)
  const [isSending, setIsSending] = useState(false)
  const [settings, setSettings] = useState(initialSettings)
  const messagesEndRef = useRef(null)

  // 새 메시지나 로딩 말풍선이 추가되면 마지막 응답으로 이동합니다.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, isSending, isOpen, activeTab])

  const requestChat = async (text) => {
    const trimmed = text.trim()
    if (!trimmed || isSending) return

    setActiveTab('chat')
    setMessages((prev) => [...prev, { role: 'user', text: trimmed }])
    setMessage('')
    setIsSending(true)

    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const token = localStorage.getItem('bobbeori-token')
      // 입력 메시지를 백엔드 챗봇 라우터로 전달합니다.
      const response = await fetch(`${apiUrl}/api/v1/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: trimmed }),
      })

      if (response.status === 401) throw new Error('unauthorized')
      if (!response.ok) throw new Error('chat request failed')

      const data = await response.json()
      setMessages((prev) => [
        ...prev,
        { role: 'bot', text: data.reply, actions: data.actions || [], sources: data.sources || [] },
      ])
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'bot',
          text:
            error.message === 'unauthorized'
              ? '로그인 토큰이 만료되었어요. 보안을 위해 일정 시간이 지나면 다시 로그인이 필요해요.'
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

  const toggleSetting = (key) => {
    setSettings((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const resetMessages = () => {
    if (window.confirm('대화를 정말 초기화할까요?')) {
      setMessages(initialMessages)
    }
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
            <button type="button" aria-label="챗봇 닫기" onClick={() => setIsOpen(false)}>
              ×
            </button>
          </header>

          {activeTab === 'home' && (
            <div className="floating-chatbot__home">
              <section className="floating-chatbot__summary" aria-labelledby="chatbot-summary-title">
                <div>
                  <span>오늘</span>
                  <h2 id="chatbot-summary-title">냉장고 요약</h2>
                </div>
                <ul>
                  <li>
                    <strong>소비 임박</strong>
                    <button type="button" onClick={() => requestChat('임박 재료 알려줘')}>
                      확인하기
                    </button>
                  </li>
                  <li>
                    <strong>추천 메뉴</strong>
                    <button type="button" onClick={() => requestChat('오늘 뭐 먹을까?')}>
                      추천받기
                    </button>
                  </li>
                </ul>
              </section>

              <section className="floating-chatbot__prompts" aria-label="추천 질문">
                <h3>추천 질문</h3>
                {quickQuestions.map((question) => (
                  <button type="button" key={question} onClick={() => requestChat(question)}>
                    {question}
                  </button>
                ))}
              </section>
            </div>
          )}

          {activeTab === 'chat' && (
            <>
              <div className="floating-chatbot__messages">
                {messages.map((item, index) => (
                  <div className={`floating-chatbot__message is-${item.role}`} key={`${item.role}-${index}`}>
                    <p>{item.text}</p>
                    {item.actions?.length ? (
                      <div className="floating-chatbot__actions">
                        {item.actions.map((action, actionIndex) => (
                          <button type="button" key={`${action.label}-${actionIndex}`} onClick={() => navigate(action.url)}>
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
                ))}
                {isSending ? (
                  <div className="floating-chatbot__message is-bot">
                    <p>...</p>
                  </div>
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
            </>
          )}

          {activeTab === 'settings' && (
            <div className="floating-chatbot__settings">
              <div className="floating-chatbot__settings-profile">
                <img src={mascot} alt="" />
                <strong>밥벌이</strong>
                <p>냉장고 도우미 챗봇</p>
              </div>

              <button type="button" onClick={() => toggleSetting('shortAnswer')}>
                <span>간단히 답변</span>
                <i className={settings.shortAnswer ? 'is-on' : ''} />
              </button>
              <button type="button" onClick={() => toggleSetting('fridgeFirst')}>
                <span>냉장고 재료 우선</span>
                <i className={settings.fridgeFirst ? 'is-on' : ''} />
              </button>
              <button type="button" onClick={() => toggleSetting('expiringFirst')}>
                <span>소비 임박 재료 우선</span>
                <i className={settings.expiringFirst ? 'is-on' : ''} />
              </button>
              <button type="button" onClick={() => toggleSetting('lowMissing')}>
                <span>부족 재료 적게</span>
                <i className={settings.lowMissing ? 'is-on' : ''} />
              </button>
              <button type="button" onClick={() => toggleSetting('excludeDislikes')}>
                <span>비선호 재료 제외</span>
                <i className={settings.excludeDislikes ? 'is-on' : ''} />
              </button>

              <button className="floating-chatbot__reset" type="button" onClick={resetMessages}>
                대화 초기화
              </button>
            </div>
          )}

          <nav className="floating-chatbot__tabs" aria-label="챗봇 메뉴">
            <button className={activeTab === 'home' ? 'is-active' : ''} type="button" onClick={() => setActiveTab('home')}>
              홈
            </button>
            <button className={activeTab === 'chat' ? 'is-active' : ''} type="button" onClick={() => setActiveTab('chat')}>
              대화
            </button>
            <button
              className={activeTab === 'settings' ? 'is-active' : ''}
              type="button"
              onClick={() => setActiveTab('settings')}
            >
              설정
            </button>
          </nav>
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