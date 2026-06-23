import React, { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom'
import Breadcrumbs from './components/Breadcrumbs.jsx'
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

  useEffect(() => {
    const hasSeen = localStorage.getItem('hasSeenOnboarding_v4');
    const token = localStorage.getItem('bobbeori-token');
    const authMode = localStorage.getItem('bobbeori-auth-mode');
    
    // 비로그인 상태이거나 이미 온보딩을 봤다면 스킵
    if (isAuthPage || hasSeen) return;

    // 정상 로그인(토큰 존재) 이거나, 소셜 모의 로그인(kakao, naver 등 - guest 제외)일 경우 띄움
    if (token || (authMode && authMode !== 'guest')) {
      setShowOnboarding(true)
    }
  }, [pathname, isAuthPage])

  return (
    <div className={isAuthPage ? 'app-shell app-shell--auth' : 'app-shell'}>
      {showOnboarding && <OnboardingModal onClose={() => setShowOnboarding(false)} />}
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
                description="밥벌이 서비스 이용 조건과 사용자 책임 범위를 안내하는 페이지입니다."
                items={[
                  '사용자는 등록한 식재료 정보와 알림 설정을 직접 확인하고 관리해야 합니다.',
                  '추천 레시피와 보관 정보는 참고용이며, 실제 섭취 가능 여부는 사용자가 최종 확인해야 합니다.',
                ]}
              />
            }
          />
          <Route
            path="/privacy-policy"
            element={
              <InfoPage
                title="개인정보처리방침"
                description="밥벌이 서비스에서 수집 및 활용할 수 있는 개인정보 처리 기준을 안내하는 페이지입니다."
                items={[
                  '소셜 로그인 정보, 알림 채널, 추천 기준 등 서비스 이용에 필요한 정보만 활용합니다.',
                  '영수증과 식재료 정보는 냉장고 관리 및 추천 기능 제공을 위해 사용됩니다.',
                ]}
              />
            }
          />
          <Route
            path="/location-policy"
            element={
              <InfoPage
                title="위치기반 서비스 약관"
                description="장보기 추천 또는 주변 구매처 안내 기능에 위치 정보가 활용될 수 있는 경우를 안내하는 페이지입니다."
                items={[
                  '현재 위치 기반 기능은 준비 중이며, 실제 적용 시 별도 동의 절차를 제공합니다.',
                  '위치 정보는 주변 구매처 안내와 가격 비교 개선 목적으로만 활용됩니다.',
                ]}
              />
            }
          />
        </Routes>
      </main>
      {!isAuthPage && <Footer />}
      {!isAuthPage && <MobileBottomNav />}
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
