import React from 'react'
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom'
import Home from './pages/home/Home.jsx'
import Fridge from './pages/fridge/Fridge.jsx'
import ReceiptOcr from './pages/receipt_ocr/ReceiptOcr.jsx'
import Guide from './pages/guide/Guide.jsx'
import RecipeRecommend from './pages/recipe_recommend/RecipeRecommend.jsx'

function App() {
  return (
    <Router>
      <div>
        <nav style={{ display: 'flex', gap: '15px', padding: '15px', borderBottom: '1px solid #ccc' }}>
          <Link to="/">홈</Link>
          <Link to="/fridge">냉장고</Link>
          <Link to="/receipt-ocr">영수증 인식</Link>
          <Link to="/guide">가이드</Link>
          <Link to="/recipe-recommend">레시피 추천</Link>
        </nav>
        <main style={{ padding: '20px' }}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/fridge" element={<Fridge />} />
            <Route path="/receipt-ocr" element={<ReceiptOcr />} />
            <Route path="/guide" element={<Guide />} />
            <Route path="/recipe-recommend" element={<RecipeRecommend />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App
