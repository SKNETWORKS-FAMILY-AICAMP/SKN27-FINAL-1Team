import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import hero1 from '../../../assets/hero_1.png'
import hero2 from '../../../assets/hero_2.png'
import hero3 from '../../../assets/hero_3.png'
import hero4 from '../../../assets/hero_4.png'
import hero5 from '../../../assets/hero_5.png'
import hero1Mobile from '../../../assets/hero_1_mobile.png'
import hero2Mobile from '../../../assets/hero_2_mobile.png'
import hero3Mobile from '../../../assets/hero_3_mobile.png'
import hero4Mobile from '../../../assets/hero_4_mobile.png'
import hero5Mobile from '../../../assets/hero_5_mobile.png'
import hero1Tablet from '../../../assets/hero_1_tablet.png'
import hero2Tablet from '../../../assets/hero_2_tablet.png'
import hero3Tablet from '../../../assets/hero_3_tablet.png'
import hero4Tablet from '../../../assets/hero_4_tablet.png'
import hero5Tablet from '../../../assets/hero_5_tablet.png'
import { getDragDirection, wrapSlideIndex } from '../heroCarousel.js'

const slides = [
  {
    image: hero3,
    mobileImage: hero3Mobile,
    tabletImage: hero3Tablet,
    eyebrow: '냉장고 관리',
    title: '재고와 소비기한을\n한눈에',
    action: '내 냉장고 보기',
    path: '/fridge',
  },
  {
    image: hero2,
    mobileImage: hero2Mobile,
    tabletImage: hero2Tablet,
    eyebrow: '영수증 등록',
    title: '영수증 한 장으로\n재료를 한 번에',
    action: '영수증 등록하기',
    path: '/receipt-ocr',
  },
  {
    image: hero1,
    mobileImage: hero1Mobile,
    tabletImage: hero1Tablet,
    eyebrow: '레시피 추천',
    title: '냉장고 재료로\n오늘의 한 끼',
    action: '메뉴 추천받기',
    path: '/recipe-fridge',
  },
  {
    image: hero4,
    mobileImage: hero4Mobile,
    tabletImage: hero4Tablet,
    eyebrow: '장보기',
    title: '추천부터 장보기까지\n한 번에',
    action: '장보기 바로가기',
    path: '/shopping-list',
  },
  {
    image: hero5,
    mobileImage: hero5Mobile,
    tabletImage: hero5Tablet,
    eyebrow: '식재료 가이드',
    title: '보관·손질 방법을\n바로 확인',
    action: '가이드 확인하기',
    path: '/guide',
  },
]

function HeroSection() {
  const [activeIndex, setActiveIndex] = useState(0)
  const dragStartXRef = useRef(null)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setActiveIndex((current) => wrapSlideIndex(current + 1, slides.length))
    }, 6000)

    return () => window.clearTimeout(timer)
  }, [activeIndex])

  const moveSlide = (direction) => {
    setActiveIndex((current) => wrapSlideIndex(current + direction, slides.length))
  }

  const handlePointerDown = (event) => {
    if (event.button !== 0 || event.target.closest('a, button')) return
    dragStartXRef.current = event.clientX
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  const handlePointerUp = (event) => {
    if (dragStartXRef.current === null) return
    const direction = getDragDirection(event.clientX - dragStartXRef.current)
    dragStartXRef.current = null
    if (direction) moveSlide(direction)
  }

  return (
    <section
      className="home-hero home-hero-slider"
      aria-label="밥벌이 서비스 소개"
      aria-roledescription="carousel"
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerCancel={() => { dragStartXRef.current = null }}
    >
      <div className="home-hero-slider__track" style={{ transform: `translateX(-${activeIndex * 100}%)` }}>
        {slides.map((slide, index) => (
          <article className="home-hero-slide" aria-hidden={activeIndex !== index} key={slide.path}>
            <picture>
              <source media="(max-width: 680px)" srcSet={slide.mobileImage} />
              <source media="(max-width: 1080px)" srcSet={slide.tabletImage} />
              <img
                className="home-hero-slide__image"
                src={slide.image}
                alt=""
                decoding="async"
                draggable="false"
                fetchPriority={index === 0 ? 'high' : 'auto'}
              />
            </picture>
            <div className="home-hero-slide__content">
              {slide.eyebrow ? <p>{slide.eyebrow}</p> : null}
              <h1>{slide.title}</h1>
              <Link to={slide.path} tabIndex={activeIndex === index ? 0 : -1}>
                {slide.action} <b aria-hidden="true">→</b>
              </Link>
            </div>
          </article>
        ))}
      </div>

      <button className="home-hero-slider__arrow is-prev" type="button" aria-label="이전 슬라이드" onClick={() => moveSlide(-1)}>
        ‹
      </button>
      <button className="home-hero-slider__arrow is-next" type="button" aria-label="다음 슬라이드" onClick={() => moveSlide(1)}>
        ›
      </button>

      <div className="home-hero-slider__dots" aria-label="슬라이드 선택">
        {slides.map((slide, index) => (
          <button
            className={activeIndex === index ? 'is-active' : ''}
            type="button"
            aria-label={`${index + 1}번 슬라이드: ${slide.eyebrow || slide.title.replace('\n', ' ')}`}
            aria-current={activeIndex === index ? 'true' : undefined}
            onClick={() => setActiveIndex(index)}
            key={slide.path}
          />
        ))}
      </div>
    </section>
  )
}

export default HeroSection
