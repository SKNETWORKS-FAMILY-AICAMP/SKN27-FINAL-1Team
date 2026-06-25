import React, { useState } from 'react'
import mascot from '../assets/mascot.png'
import './FloatingChatbot.css'

const initialSettings = {
  shortAnswer: true,
  fridgeFirst: true,
  expiringFirst: true,
  lowMissing: true,
  excludeDislikes: true,
}

function FloatingChatbot() {
  const [isOpen, setIsOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('chat')
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState([
    { role: 'bot', text: '안녕하세요. 레시피, 보관법, 장보기를 도와드릴게요.' },
  ])
  const [settings, setSettings] = useState(initialSettings)

  const sendMessage = (event) => {
    event.preventDefault()
    const text = message.trim()
    if (!text) return

    setMessages((prev) => [
      ...prev,
      { role: 'user', text },
      { role: 'bot', text: '아직 챗봇 연결 전이에요. 곧 실제 기능과 연결할게요.' },
    ])
    setMessage('')
  }

  const toggleSetting = (key) => {
    setSettings((prev) => ({ ...prev, [key]: !prev[key] }))
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
            <div className="floating-chatbot__empty">
              <img src={mascot} alt="" />
              <strong>밥벌이에게 물어보세요</strong>
              <p>레시피, 보관법, 장보기까지 한 곳에서 도와드릴게요.</p>
            </div>
          )}

          {activeTab === 'chat' && (
            <>
              <div className="floating-chatbot__messages">
                {messages.map((item, index) => (
                  <p className={`floating-chatbot__message is-${item.role}`} key={`${item.role}-${index}`}>
                    {item.text}
                  </p>
                ))}
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

              <button className="floating-chatbot__reset" type="button" onClick={() => setMessages([])}>
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
