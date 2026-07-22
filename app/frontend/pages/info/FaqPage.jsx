import React from 'react'
import './InfoPage.css'

export const faqGroups = [
  {
    title: '영수증',
    description: '영수증 업로드, 인식 결과 확인, 냉장고 입고 관련 질문입니다.',
    questions: [
      {
        question: '영수증을 올리면 바로 냉장고에 저장되나요?',
        answer: '아니요. 업로드한 영수증에서 추출된 품목을 사용자가 먼저 확인하고, 선택한 항목만 냉장고에 저장됩니다.',
      },
      {
        question: '인식된 재료명이 틀리면 수정할 수 있나요?',
        answer: '네. 냉장고에 입고하기 전에 재료명, 수량, 단위, 구매일, 소비기한 등을 직접 수정할 수 있습니다.',
      },
      {
        question: '카드전표처럼 품목이 없는 영수증도 등록할 수 있나요?',
        answer: '품목 목록이 없는 영수증은 자동 인식이 어려울 수 있습니다. 이 경우 필요한 재료를 직접 추가해 냉장고에 입고할 수 있습니다.',
      },
      {
        question: '영수증 이미지는 어디에 보관되나요?',
        answer: '운영 환경에서는 영수증 이미지가 전용 저장소에 보관되며, 영수증 내역 삭제 또는 계정 삭제 요청 시 정책에 따라 함께 처리됩니다.',
      },
    ],
  },
  {
    title: '냉장고',
    description: '재료 등록, 보관 위치, 소비기한, 수량 관리 관련 질문입니다.',
    questions: [
      {
        question: '냉장고 재료는 어떻게 등록하나요?',
        answer: '직접 입력하거나, 영수증 등록 결과에서 확인한 품목을 선택해 냉장고에 입고할 수 있습니다.',
      },
      {
        question: '소비기한은 자동으로 계산되나요?',
        answer: '구매일, 보관 위치, 재료 정보를 기준으로 예상 소비기한을 제안합니다. 실제 상태와 다를 수 있어 사용자가 직접 수정할 수 있습니다.',
      },
      {
        question: '냉장/냉동/실온 보관 위치를 바꿀 수 있나요?',
        answer: '네. 재료 수정 화면에서 보관 위치, 수량, 단위, 소비기한을 변경할 수 있습니다.',
      },
      {
        question: '재료를 사용하면 수량도 줄어드나요?',
        answer: '저장된 레시피에서 요리 완료를 누르면 사용한 재료 수량을 확인한 뒤 냉장고 수량에 반영할 수 있습니다.',
      },
    ],
  },
  {
    title: '레시피',
    description: '냉장고 파먹기, 추천 레시피, 저장 레시피 관련 질문입니다.',
    questions: [
      {
        question: '냉장고 파먹기 추천은 어떤 기준으로 나오나요?',
        answer: '현재 보유 중인 재료와 소비기한이 임박한 재료를 기준으로 만들기 좋은 메뉴를 추천합니다.',
      },
      {
        question: '냉장고에 없는 재료가 필요한 레시피도 추천되나요?',
        answer: '일부 부족한 재료가 있는 레시피도 추천될 수 있습니다. 부족한 재료는 장보기 목록에서 따로 확인할 수 있습니다.',
      },
      {
        question: '추천받은 레시피를 저장할 수 있나요?',
        answer: '네. 마음에 드는 레시피를 저장해두고 마이페이지에서 다시 확인할 수 있습니다.',
      },
      {
        question: '요리 완료를 누르면 어떤 일이 일어나나요?',
        answer: '레시피에 사용된 재료와 수량을 확인한 뒤, 냉장고 재료 수량을 차감하고 저장된 레시피 목록에서 정리할 수 있습니다.',
      },
    ],
  },
  {
    title: '캘린더',
    description: 'Google Calendar 연동, 알림 일정, 연동 해제 관련 질문입니다.',
    questions: [
      {
        question: 'Google Calendar를 연결하면 무엇이 등록되나요?',
        answer: '소비 임박 재료 확인, 오늘의 추천 메뉴, 레시피 삭제 예정 알림, 영수증 등록 완료 기록 등을 캘린더 일정으로 등록할 수 있습니다.',
      },
      {
        question: '알림 항목은 직접 켜고 끌 수 있나요?',
        answer: '네. 마이페이지의 알림 및 캘린더 설정에서 필요한 알림만 선택해 사용할 수 있습니다.',
      },
      {
        question: '캘린더 연동을 해제할 수 있나요?',
        answer: '네. 마이페이지에서 Google Calendar 연동을 해제할 수 있습니다. 해제 후에는 새 알림 일정이 등록되지 않습니다.',
      },
      {
        question: '주말과 공휴일도 확인할 수 있나요?',
        answer: '밥벌이 캘린더 화면에서 주말과 공휴일을 구분해 확인할 수 있어, 쉬는 날 요리 계획을 세우는 데 활용할 수 있습니다.',
      },
    ],
  },
  {
    title: 'MCP',
    description: 'ChatGPT, Codex, 외부 Agent 연결과 권한 관련 질문입니다.',
    questions: [
      {
        question: 'ChatGPT에서 밥벌이를 연결하면 무엇을 할 수 있나요?',
        answer: '냉장고 재료 조회, 소비 임박 재료 확인, 레시피 추천, 장보기 목록 작성, 캘린더 일정 생성 등을 대화로 사용할 수 있습니다.',
      },
      {
        question: 'MCP 연결은 밥벌이 계정과 어떻게 연결되나요?',
        answer: 'OAuth 로그인을 통해 사용자의 밥벌이 계정과 연결되며, 허용한 권한 범위 안에서만 기능을 사용할 수 있습니다.',
      },
      {
        question: 'ChatGPT가 바로 데이터를 수정하나요?',
        answer: '중요한 쓰기 작업은 미리보기 후 사용자의 확인을 거쳐 저장되도록 구성되어 있습니다.',
      },
      {
        question: '외부 Agent가 제 데이터를 마음대로 볼 수 있나요?',
        answer: '아니요. 인증된 사용자와 승인된 권한 범위 안에서만 접근할 수 있으며, 필요한 범위만 요청하도록 설계되어 있습니다.',
      },
    ],
  },
]

function FaqPage() {
  return (
    <div className="page-container faq-page">
      <header className="faq-page__header">
        <h1>자주 묻는 질문</h1>
        <p>밥벌이 서비스 이용 중 자주 묻는 질문을 기능별로 정리했습니다.</p>
      </header>

      <div className="faq-group-list">
        {faqGroups.map((group) => (
          <details className="faq-group" key={group.title}>
            <summary>
              <span>
                <strong>{group.title}</strong>
                <small>{group.description}</small>
              </span>
            </summary>

            <div className="faq-question-list">
              {group.questions.map((item) => (
                <details className="faq-question" key={item.question}>
                  <summary>{item.question}</summary>
                  <p>{item.answer}</p>
                </details>
              ))}
            </div>
          </details>
        ))}
      </div>
    </div>
  )
}

export default FaqPage
