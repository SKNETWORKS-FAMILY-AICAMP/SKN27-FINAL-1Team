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

const quickQuestions = [
  { icon: 'search', label: '양파 보관법' },
  { icon: 'clock', label: '임박 재료 알려줘' },
  { icon: 'bowl', label: '오늘의 추천 메뉴', randomMenu: true },
]

const randomMenus = ['김치볶음밥', '계란볶음밥', '두부김치', '참치마요주먹밥', '파스타', '된장찌개']


// 챗봇 UI에서 폰트 영향을 받지 않는 작은 SVG 아이콘을 렌더링합니다.
function ChatIcon({ name }) {
  const common = { className: 'floating-chatbot__icon', viewBox: '0 0 24 24', 'aria-hidden': 'true' }

  if (name === 'summary') {
    return (
      <svg {...common}>
        <rect x="7" y="5" width="10" height="14" rx="1.5" />
        <path d="M10 9h4M10 13h4" />
        <path d="M9 5v14" />
      </svg>
    )
  }

  if (name === 'clock') {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="7" />
        <path d="M12 8v5l3 2" />
      </svg>
    )
  }

  if (name === 'steam') {
    return (
      <svg {...common}>
        <path d="M8 9c-1.5 1.6-1.5 3.1 0 4.6M12 7.5c-1.8 2-1.8 4 0 6M16 9c-1.5 1.6-1.5 3.1 0 4.6" />
        <path d="M6 15h12l-1.5 3h-9L6 15Z" />
      </svg>
    )
  }

  if (name === 'light') {
    return (
      <svg {...common}>
        <path d="M9 18h6" />
        <path d="M10 21h4" />
        <path d="M8.5 13.5c-1.2-1-2-2.4-2-4A5.5 5.5 0 0 1 12 4a5.5 5.5 0 0 1 5.5 5.5c0 1.6-.8 3-2 4-.8.7-1 1.3-1 2.5h-5c0-1.2-.2-1.8-1-2.5Z" />
      </svg>
    )
  }

  if (name === 'search') {
    return (
      <svg {...common}>
        <circle cx="10.5" cy="10.5" r="5.5" />
        <path d="m15 15 4 4" />
      </svg>
    )
  }

  if (name === 'bowl') {
    return (
      <svg {...common}>
        <path d="M7 10c0-2 2-2 2-4M12 10c0-2 2-2 2-4" />
        <path d="M5 12h14l-1.5 5h-11L5 12Z" />
        <path d="M8 19h8" />
      </svg>
    )
  }

  if (name === 'home') {
    return (
      <svg {...common}>
        <path d="M4 11 12 5l8 6" />
        <path d="M7 10.5V19h10v-8.5" />
        <path d="M10 19v-5h4v5" />
      </svg>
    )
  }

  if (name === 'chat') {
    return (
      <svg {...common}>
        <circle cx="8.5" cy="11" r="1" />
        <circle cx="12" cy="11" r="1" />
        <circle cx="15.5" cy="11" r="1" />
        <path d="M5 5.8h14v10H9l-4 3v-13Z" />
      </svg>
    )
  }

  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v3M12 18v3M4.2 7.5l2.6 1.5M17.2 15l2.6 1.5M4.2 16.5 6.8 15M17.2 9l2.6-1.5" />
    </svg>
  )
}

// 봇 메시지를 한 글자씩 타이핑하듯 보여주는 애니메이션 컴포넌트입니다.
function TypewriterMessage({ text, onTyping, onComplete }) {
  const [displayedText, setDisplayedText] = useState('');

  useEffect(() => {
    setDisplayedText('');
    let index = 0;
    const interval = setInterval(() => {
      setDisplayedText(text.slice(0, index + 1));
      index++;
      if (index >= text.length) {
        clearInterval(interval);
        if (onComplete) {
          onComplete();
        }
      }
    }, 30); // 30ms 간격으로 글자 출력 (자연스러운 LLM 속도)
    return () => clearInterval(interval);
  }, [text]);

  useEffect(() => {
    if (onTyping) {
      onTyping();
    }
  }, [displayedText, onTyping]);

  return <p style={{ whiteSpace: 'pre-wrap' }}>{displayedText}</p>;
}

// 소비기한 D-day를 홈 카드에 표시할 짧은 문구로 바꿉니다.
function getDdayLabel(dDay) {
  if (dDay > 0) return `D-${dDay}`
  if (dDay === 0) return 'D-Day'
  return `D+${Math.abs(dDay)}`
}

// API 응답에서 D-day가 없을 때 날짜로 보정합니다.
function getItemDday(item) {
  if (item.d_day !== null && item.d_day !== undefined) return item.d_day
  if (!item.expiration_date) return null

  const target = new Date(item.expiration_date)
  if (Number.isNaN(target.getTime())) return null

  const today = new Date()
  today.setHours(0, 0, 0, 0)
  target.setHours(0, 0, 0, 0)
  return Math.ceil((target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
}

function FloatingChatbot() {
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('home')
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState(initialMessages)
  const [isSending, setIsSending] = useState(false)
  const [settings, setSettings] = useState(initialSettings)
  const [expiringItems, setExpiringItems] = useState([])
  const [inventoryCount, setInventoryCount] = useState(null)
  const [recommendedMenu, setRecommendedMenu] = useState('추천 메뉴 확인 중')
  const messagesEndRef = useRef(null)

  // 새 메시지나 로딩 말풍선이 추가되면 마지막 응답으로 이동합니다.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, isSending, isOpen, activeTab])

  // 홈 요약에 보여줄 소비 임박 재료 3개만 기존 냉장고 API에서 가져옵니다.
  useEffect(() => {
    if (!isOpen) return

    const fetchExpiringItems = async () => {
      try {
        const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
        const token = localStorage.getItem('bobbeori-token')
        const response = await fetch(`${apiUrl}/api/v1/inventory`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!response.ok) return

        const data = await response.json()
        setInventoryCount(data.length)
        const nextItems = data
          .map((item) => ({ ...item, d_day: getItemDday(item) }))
          .filter((item) => item.d_day !== null && item.d_day >= 0 && item.d_day <= 3)
          .sort((a, b) => a.d_day - b.d_day)
          .slice(0, 3)
        setExpiringItems(nextItems)

        if (data.length === 0) {
          setRecommendedMenu('식재료가 없습니다')
          return
        }

        const recommendResponse = await fetch(`${apiUrl}/api/v1/recipes/recommend`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ mode: 'fridge_consume' }),
        })
        if (!recommendResponse.ok) return

        const recommendData = await recommendResponse.json()
        setRecommendedMenu(recommendData.items?.[0]?.title || '추천 메뉴 없음')
      } catch (error) {
        setInventoryCount(null)
        setExpiringItems([])
        setRecommendedMenu('추천 메뉴 없음')
      }
    }

    fetchExpiringItems()
  }, [isOpen])

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
              ? '로그인 토큰이 만료되었어요. 보안을 위해 일정 시간이 지나면 다시 로그인이 필요해요.'
              : '챗봇 연결 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.',
        },
      ])
    } finally {
      setIsSending(false)
    }
  }

  // 추천 질문의 오늘 메뉴는 백엔드 1순위 고정 추천 대신 가벼운 랜덤 메뉴로 답합니다.
  const handleQuickQuestion = (question) => {
    if (!question.randomMenu) {
      requestChat(question.label)
      return
    }

    const menu = randomMenus[Math.floor(Math.random() * randomMenus.length)]
    setActiveTab('chat')
    setMessages((prev) => [
      ...prev,
      { role: 'user', text: question.label },
      {
        role: 'bot',
        isTyping: true,
        text: `오늘은 ${menu} 어때요? \n레시피 페이지에서 바로 찾아볼 수 있어요.`,
        actions: [{ label: `${menu} 레시피 보기`, url: `/recipes?query=${encodeURIComponent(menu)}` }],
      },
    ])
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
                <div className="floating-chatbot__summary-title">
                  <span className="floating-chatbot__summary-title-icon" aria-hidden="true">
                    <ChatIcon name="summary" />
                  </span>
                  <h2 id="chatbot-summary-title">오늘의 냉장고 요약</h2>
                </div>
                <ul>
                  <li>
                    <span className="floating-chatbot__summary-icon is-danger" aria-hidden="true">
                      <ChatIcon name="clock" />
                    </span>
                    <strong>소비 임박</strong>
                    {expiringItems.length ? (
                      <p className="floating-chatbot__summary-chips">
                        {expiringItems.map((item) => (
                          <span key={item.fridge_id || item.id}>{item.name} {getDdayLabel(item.d_day)}</span>
                        ))}
                      </p>
                    ) : (
                      <p>{inventoryCount === 0 ? '식재료가 없습니다' : '임박 재료 없음'}</p>
                    )}
                    <button type="button" aria-label="임박 재료 확인" onClick={() => requestChat('임박 재료 알려줘')}>
                      ›
                    </button>
                  </li>
                  <li>
                    <span className="floating-chatbot__summary-icon is-menu" aria-hidden="true">
                      <ChatIcon name="bowl" />
                    </span>
                    <strong>추천 메뉴</strong>
                    <p>{recommendedMenu}</p>
                    <button type="button" aria-label="추천 메뉴 확인" onClick={() => requestChat('오늘의 추천 메뉴')}>
                      ›
                    </button>
                  </li>
                </ul>
              </section>

              <section className="floating-chatbot__prompts" aria-label="추천 질문">
                <h3><span aria-hidden="true"><ChatIcon name="light" /></span> 추천 질문</h3>
                {quickQuestions.map((question) => (
                  <button type="button" key={question.label} onClick={() => handleQuickQuestion(question)}>
                    <span className="floating-chatbot__prompt-icon" aria-hidden="true">
                      <ChatIcon name={question.icon} />
                    </span>
                    {question.label}
                  </button>
                ))}
              </section>
            </div>
          )}

          {activeTab === 'chat' && (
            <>
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
                              setMessages(prev => {
                                const next = [...prev];
                                next[index] = { ...next[index], isTyping: false };
                                return next;
                              })
                            }}
                          />
                        ) : (
                          <p style={{ whiteSpace: 'pre-wrap' }}>{item.text}</p>
                        )
                      ) : (
                        <p>{item.text}</p>
                      )}
                      {item.actions?.length ? (
                        <div className="floating-chatbot__actions">
                          {item.actions.map((action, actionIndex) => (
                            <button
                              type="button"
                              key={`${action.label}-${actionIndex}`}
                              onClick={() => action.url && navigate(action.url)}
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
                      <p>...</p>
                    </div>
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
              <span aria-hidden="true"><ChatIcon name="home" /></span>
              홈
            </button>
            <button className={activeTab === 'chat' ? 'is-active' : ''} type="button" onClick={() => setActiveTab('chat')}>
              <span aria-hidden="true"><ChatIcon name="chat" /></span>
              대화
            </button>
            <button
              className={activeTab === 'settings' ? 'is-active' : ''}
              type="button"
              onClick={() => setActiveTab('settings')}
            >
              <span aria-hidden="true"><ChatIcon name="settings" /></span>
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