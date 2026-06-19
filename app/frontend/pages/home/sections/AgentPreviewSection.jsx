const agents = [
  'Receipt OCR Agent',
  'Inventory Agent',
  'Recipe Agent',
  'Recommendation Agent',
  'Shopping/Price Agent',
  'Notification Agent',
  'Supervisor Agent',
]

const previews = ['냉장고 화면', '영수증 OCR 화면', '냉장고파먹기 화면', '장보기 화면']

function AgentPreviewSection() {
  return (
    <section className="home-section home-agent-preview" aria-label="AI Agent와 화면 미리보기">
      <div className="home-agent-block">
        <h2>여러 AI Agent가 함께 일해요</h2>
        <div className="home-agent-row">
          {agents.map((agent, index) => (
            <div className="home-agent-card" key={agent}>
              <span className="image-slot image-slot--agent" aria-hidden="true" />
              <strong>{agent}</strong>
              {index < agents.length - 1 && <i aria-hidden="true" />}
            </div>
          ))}
        </div>
      </div>

      <div className="home-preview-block">
        <h2>화면 미리보기</h2>
        <div className="home-preview-grid">
          {previews.map((preview) => (
            <article className="home-preview-card" key={preview}>
              <strong>{preview}</strong>
              <span className="image-slot image-slot--preview" aria-hidden="true" />
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

export default AgentPreviewSection
