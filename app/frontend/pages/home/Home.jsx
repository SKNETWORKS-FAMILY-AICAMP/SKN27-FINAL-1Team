import { useEffect } from 'react'
import './Home.css'
import HeroSection from './sections/HeroSection'
import AppIntroSection from './sections/AppIntroSection'
import WeeklyRecipeSection from './sections/WeeklyRecipeSection'
import HomeFaqSection from './sections/HomeFaqSection'
import ReviewSection from './sections/ReviewSection'

function Home() {
  useEffect(() => {
    const revealTargets = document.querySelectorAll('.home-reveal')

    if (!('IntersectionObserver' in window)) {
      revealTargets.forEach((target) => target.classList.add('show'))
      return undefined
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return
          entry.target.classList.add('show')
          observer.unobserve(entry.target)
        })
      },
      {
        rootMargin: '0px 0px -12% 0px',
        threshold: 0.14,
      },
    )

    revealTargets.forEach((target) => observer.observe(target))

    return () => observer.disconnect()
  }, [])

  return (
    <div className="home-page">
      <HeroSection />
      <AppIntroSection />
      <WeeklyRecipeSection />
      <HomeFaqSection />
      <ReviewSection />
    </div>
  )
}

export default Home
