import appIcon from '../../../assets/app_icon.png'
import googlePlayBadge from '../../../assets/google_play_badge_ko.png'

const APP_STORE_URL = 'https://play.google.com/store/apps/details?id=com.bobbeori.bobbeori_app'

function AppIntroSection() {
  return (
    <section className="home-app-intro home-reveal" aria-labelledby="home-app-title">
      <div className="home-app-intro__inner">
        <div className="home-app-intro__copy">
          <p>밥벌이 음성 챗봇</p>
          <h2 id="home-app-title">
            요리 중에도
            <br />
            음성으로 안내받으세요
          </h2>
          <span>손이 바쁜 순간에도 조리 순서와 다음 단계를 말로 묻고 바로 안내받을 수 있어요.</span>
          <a
            className="home-app-intro__store-badge"
            href={APP_STORE_URL}
            target="_blank"
            rel="noreferrer"
            aria-label="Google Play에서 밥벌이 다운로드"
          >
            <img src={googlePlayBadge} alt="Google Play에서 다운로드" />
          </a>
        </div>

        <div className="home-app-intro__visual" aria-hidden="true">
          <span className="home-app-intro__voice-pulse" />
          <div className="home-app-intro__voice-content">
            <img src={appIcon} alt="" />
            <div className="home-app-intro__voice-wave">
              {[0, 1, 2, 3, 4].map((bar) => <i key={bar} />)}
            </div>
            <strong>음성 안내 중</strong>
            <span>“다음 단계를 알려드릴게요”</span>
          </div>
        </div>
      </div>
    </section>
  )
}

export default AppIntroSection
