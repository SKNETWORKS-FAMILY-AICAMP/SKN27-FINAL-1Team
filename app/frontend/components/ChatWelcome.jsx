import React, { useEffect, useState } from 'react';
import './ChatWelcome.css';

function ChatWelcome({ onRequestChat }) {
  const suggestions = [
    "오늘 뭐 해먹지?",
    "소비 임박재료 뭐 있어?",
    "냉장고에 뭐 있지?",
  ];

  return (
    <div className="chat-welcome">

      <div className="chat-welcome__suggestions">
        <p>이런 질문은 어떠세요?</p>
        <div className="chat-welcome__chips">
          {suggestions.map((q, idx) => (
            <button key={idx} className="chat-welcome__chip" onClick={() => onRequestChat(q)}>
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default ChatWelcome;
