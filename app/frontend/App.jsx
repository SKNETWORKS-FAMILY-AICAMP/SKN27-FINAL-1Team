import React, { useEffect, useState } from 'react'
import { BrowserRouter as Router, Navigate, Routes, Route, useLocation } from 'react-router-dom'
import { API_URL } from './utils/api.js'
import Breadcrumbs from './components/Breadcrumbs.jsx'
import FloatingChatbot from './components/FloatingChatbot.jsx'
import Footer from './components/Footer.jsx'
import Header from './components/Header.jsx'
import MobileBottomNav from './components/MobileBottomNav.jsx'
import OnboardingModal from './components/OnboardingModal.jsx'
import Home from './pages/home/Home.jsx'
import InfoPage from './pages/info/InfoPage.jsx'
import Login from './pages/login/Login.jsx'
import Callback from './pages/login/Callback.jsx'
import Mypage from './pages/mypage/Mypage.jsx'
import Fridge from './pages/fridge/Fridge.jsx'
import ReceiptOcr from './pages/receipt_ocr/ReceiptOcr.jsx'
import Guide from './pages/guide/Guide.jsx'
import FridgeRecipe from './pages/fridge_recipe/FridgeRecipe.jsx'
import RecipeDetail from './pages/recipe_detail/RecipeDetail.jsx'
import RecipeList from './pages/recipe_list/RecipeList.jsx'
import MenuRecommend from './pages/menu_recommend/MenuRecommend.jsx'
import RecipeRecommend from './pages/recipe_recommend/RecipeRecommend.jsx'
import ShoppingList from './pages/shopping_list/ShoppingList.jsx'

function AppLayout() {
  const { pathname } = useLocation()
  const isAuthPage = pathname === '/login' || pathname.startsWith('/auth/callback')
  
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [onboardingSeenKey, setOnboardingSeenKey] = useState('hasSeenOnboarding_v4')

  useEffect(() => {
    const token = localStorage.getItem('bobbeori-token')
    const authMode = localStorage.getItem('bobbeori-auth-mode')

    // 인증 페이지, 비로그인, 게스트는 온보딩 자동 노출 대상에서 제외합니다.
    if (isAuthPage || !token || authMode === 'guest') return

    let isCancelled = false

    // 현재 로그인한 사용자 기준으로 온보딩 완료 여부를 확인합니다.
    fetch(`${API_URL}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((user) => {
        if (!user || isCancelled) return
        const seenKey = `hasSeenOnboarding_v4_${user.id}`
        setOnboardingSeenKey(seenKey)
        if (!user.is_onboarded && !localStorage.getItem(seenKey)) {
          setShowOnboarding(true)
        }
      })
      .catch(() => {})

    return () => {
      isCancelled = true
    }
  }, [pathname, isAuthPage])

  return (
    <div className={isAuthPage ? 'app-shell app-shell--auth' : 'app-shell'}>
      {showOnboarding && <OnboardingModal seenKey={onboardingSeenKey} onClose={() => setShowOnboarding(false)} />}
      {!isAuthPage && <Header />}
      <main className={isAuthPage ? 'app-main app-main--auth' : 'app-main'}>
        {!isAuthPage && <Breadcrumbs />}
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/fridge" element={<Fridge />} />
          <Route path="/receipt-ocr" element={<ReceiptOcr />} />
          <Route path="/recipes" element={<RecipeList />} />
          <Route path="/recipes/:recipeId" element={<RecipeDetail />} />
          <Route path="/guide" element={<Guide />} />
          <Route path="/guide/:ingredientName" element={<Guide />} />
          <Route path="/recipe-fridge" element={<FridgeRecipe />} />
          <Route path="/menu-recommend" element={<MenuRecommend />} />
          <Route path="/recipe-recommend" element={<RecipeRecommend />} />
          <Route path="/login" element={<Login />} />
          <Route path="/auth/callback/:provider" element={<Callback />} />
          <Route path="/mypage" element={<Mypage />} />
          <Route path="/shopping-list" element={<ShoppingList />} />
          <Route
            path="/faq"
            element={
              <InfoPage
                title="자주 묻는 질문"
                description="밥벌이 서비스 이용 중 자주 묻는 질문을 정리하는 페이지입니다."
                items={[
                  '영수증 등록 후 추출된 재료는 사용자가 확인한 항목만 냉장고에 저장됩니다.',
                  '냉장고 파먹기 추천은 보유 재료와 소비 임박 재료를 기준으로 동작합니다.',
                  '장보기 리스트는 추천 레시피에서 부족한 재료를 기준으로 구성됩니다.',
                ]}
              />
            }
          />
          <Route
            path="/support"
            element={
              <InfoPage
                title="고객 지원"
                description="서비스 문의, 오류 제보, 개선 제안을 접수하는 안내 페이지입니다."
                items={[
                  '문의 이메일: bobbeori@bobbeori.com',
                  '오류 제보 시 발생 화면, 사용 브라우저, 재현 순서를 함께 보내주시면 확인이 빠릅니다.',
                ]}
              />
            }
          />
          <Route
            path="/refund-policy"
            element={
              <InfoPage
                title="반품 및 환불 정책"
                description="유료 기능 또는 외부 구매 연동 시 적용될 환불 기준을 안내하는 페이지입니다."
                items={[
                  '현재 밥벌이는 직접 상품을 판매하지 않으며, 외부 마켓 구매 및 환불은 각 판매처 정책을 따릅니다.',
                  '향후 유료 기능이 제공될 경우 결제 취소와 환불 기준을 별도로 고지합니다.',
                ]}
              />
            }
          />
          <Route
            path="/terms"
            element={
              <InfoPage
                title="이용약관"
                description="밥벌이 서비스 이용에 필요한 기본 조건을 안내합니다."
                items={[
                  '밥벌이는 냉장고 재료 관리, 영수증 OCR 입고, 레시피 추천, 장보기 목록, 캘린더 알림 기능을 제공합니다.',
                  '사용자는 본인이 등록한 식재료, 영수증, 레시피 저장 정보가 정확한지 직접 확인하고 관리해야 합니다.',
                  '레시피 추천, 식재료 가이드, 유통기한 알림은 참고용 정보이며 실제 섭취 가능 여부는 사용자가 최종 판단해야 합니다.',
                  '타인의 계정 또는 정보를 무단으로 사용하거나 서비스 운영을 방해하는 행위는 제한될 수 있습니다.',
                  '서비스 내용은 개선을 위해 변경될 수 있으며, 중요한 변경 사항은 서비스 화면 또는 공지로 안내합니다.',
                  '문의: bobbeori@bobbeori.com',
                ]}
              />
            }
          />
          <Route
            path="/privacy"
            element={
              <InfoPage
                title="개인정보처리방침"
                description="밥벌이가 서비스 제공을 위해 처리하는 개인정보 기준입니다."
                items={[
                  '수집 항목: 소셜 로그인 식별 정보, 이메일, 닉네임, 냉장고 재료, 영수증 OCR 결과, 저장 레시피, 알림 및 캘린더 연동 설정.',
                  '이용 목적: 회원 식별, 냉장고 재료 관리, 레시피 추천, 장보기 목록 생성, Google Calendar 알림 등록, 고객 문의 대응.',
                  'Google Calendar 연동 시 사용자가 동의한 범위 안에서 밥벌이 알림 일정을 생성하고 조회합니다.',
                  '위치정보는 수집하거나 사용하지 않습니다.',
                  '개인정보는 서비스 이용 기간 동안 보관하며, 회원 탈퇴 또는 삭제 요청 시 관계 법령상 보관이 필요한 경우를 제외하고 삭제합니다.',
                  '개인정보 처리 관련 문의 및 삭제 요청: bobbeori@bobbeori.com',
                ]}
              />
            }
          />
          <Route path="/privacy-policy" element={<Navigate to="/privacy" replace />} />
        </Routes>
      </main>
      {!isAuthPage && <Footer />}
      {!isAuthPage && <MobileBottomNav />}
      {!isAuthPage && <FloatingChatbot />}
    </div>
  )
}

function App() {
  return (
    <Router>
      <AppLayout />
    </Router>
  )
}

export default App
