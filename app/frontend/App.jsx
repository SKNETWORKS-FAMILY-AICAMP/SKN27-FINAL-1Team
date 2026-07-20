import React, { useEffect, useState } from 'react'
import { BrowserRouter as Router, Navigate, Routes, Route, useLocation, useNavigate } from 'react-router-dom'
import {
  API_NOTICE_EVENT,
  API_URL,
  SESSION_EXPIRED_KEY,
  authenticatedFetch,
  isSessionExpiredError,
} from './utils/api.js'
import Breadcrumbs from './components/Breadcrumbs.jsx'
import FloatingChatbot from './components/FloatingChatbot.jsx'
import Footer from './components/Footer.jsx'
import Header from './components/Header.jsx'
import MobileBottomNav from './components/MobileBottomNav.jsx'
import OnboardingModal from './components/OnboardingModal.jsx'
import ConfirmModal from './components/modals/ConfirmModal.jsx'
import Home from './pages/home/Home.jsx'
import InfoPage from './pages/info/InfoPage.jsx'
import { privacyDocument, termsDocument } from './pages/info/policyContent.js'
import Login from './pages/login/Login.jsx'
import Callback from './pages/login/Callback.jsx'
import Mypage from './pages/mypage/Mypage.jsx'
import Fridge from './pages/fridge/Fridge.jsx'
import ReceiptOcr from './pages/receipt_ocr/ReceiptOcr.jsx'
import Guide from './pages/guide/Guide.jsx'
import FridgeRecipe from './pages/fridge_recipe/FridgeRecipe.jsx'
import RecipeDetail from './pages/recipe_detail/RecipeDetail.jsx'
import RecipeList from './pages/recipe_list/RecipeList.jsx'
import RecipeRecommend from './pages/recipe_recommend/RecipeRecommend.jsx'
import ShoppingList from './pages/shopping_list/ShoppingList.jsx'


function AppLayout() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const isAuthPage = pathname === '/login' || pathname.startsWith('/auth/callback')
  
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [onboardingSeenKey, setOnboardingSeenKey] = useState('hasSeenOnboarding_v4')
  const [apiNotice, setApiNotice] = useState(null)


  useEffect(() => {
    // API 오류를 서비스 디자인 모달로 안내하고 세션 만료는 한 번만 표시합니다.
    const handleApiNotice = (event) => {
      if (event.detail?.type === 'sessionExpired') {
        if (sessionStorage.getItem(SESSION_EXPIRED_KEY)) return
        sessionStorage.setItem(SESSION_EXPIRED_KEY, 'true')
      }
      setApiNotice(event.detail)
    }

    window.addEventListener(API_NOTICE_EVENT, handleApiNotice)
    return () => window.removeEventListener(API_NOTICE_EVENT, handleApiNotice)
  }, [])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  useEffect(() => {
    const token = localStorage.getItem('bobbeori-token')

    // 인증 페이지 및 비로그인은 온보딩 자동 노출 대상에서 제외합니다.
    if (isAuthPage || pathname === '/mypage' || !token) return

    let isCancelled = false

    // 현재 로그인한 사용자 기준으로 온보딩 완료 여부를 확인합니다.
    authenticatedFetch(`${API_URL}/api/v1/auth/me`)
      .then((res) => {
        return res.ok ? res.json() : null
      })
      .then((user) => {
        if (!user || isCancelled) return
        const seenKey = `hasSeenOnboarding_v4_${user.id}`
        setOnboardingSeenKey(seenKey)
        if (!user.is_onboarded && !localStorage.getItem(seenKey)) {
          setShowOnboarding(true)
        }
      })
      .catch((error) => {
        if (isSessionExpiredError(error)) navigate('/login')
      })

    return () => {
      isCancelled = true
    }
  }, [pathname, isAuthPage, navigate])

  // 세션 만료 안내를 닫으면 로그인 화면으로 이동합니다.
  const closeApiNotice = () => {
    const shouldRedirectToLogin = apiNotice?.type === 'sessionExpired'
    setApiNotice(null)
    if (shouldRedirectToLogin) navigate('/login')
  }

  return (
    <div className={isAuthPage ? 'app-shell app-shell--auth' : 'app-shell'}>
      {showOnboarding && <OnboardingModal seenKey={onboardingSeenKey} onClose={() => setShowOnboarding(false)} />}

      <ConfirmModal
        isOpen={Boolean(apiNotice)}
        title={apiNotice?.title || '알림'}
        message={apiNotice?.message || ''}
        confirmText="확인"
        showCancel={false}
        onConfirm={closeApiNotice}
        onClose={closeApiNotice}
      />
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
            element={<InfoPage {...termsDocument} />}
          />
          <Route
            path="/privacy"
            element={<InfoPage {...privacyDocument} />}
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
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppLayout />
    </Router>
  )
}

export default App
