import React from 'react'
import './InfoPage.css'

function InfoPage({ title, description, items = [], effectiveDate, revisedDate, notice, sections = [] }) {
  const isDocument = sections.length > 0

  return (
    <div className={`page-container${isDocument ? ' info-page--document' : ''}`}>
      <header className={isDocument ? 'info-document-header' : undefined}>
        {isDocument ? <span>POLICY &amp; LEGAL</span> : null}
        <h1>{title}</h1>
        <p>{description}</p>
        {isDocument ? (
          <dl className="info-document-meta">
            <div><dt>시행일</dt><dd>{effectiveDate}</dd></div>
            <div><dt>최종 개정일</dt><dd>{revisedDate}</dd></div>
          </dl>
        ) : null}
      </header>

      {isDocument ? (
        <div className="info-document-layout">
          <nav className="info-document-toc" aria-label={`${title} 목차`}>
            <strong>목차</strong>
            <ol>
              {sections.map((section, index) => (
                <li key={section.title}><a href={`#policy-section-${index + 1}`}>{section.title}</a></li>
              ))}
            </ol>
          </nav>

          <article className="info-document">
            {notice ? <p className="info-document-notice">{notice}</p> : null}
            {sections.map((section, index) => (
              <section id={`policy-section-${index + 1}`} key={section.title}>
                <div className="info-document-section-title">
                  <span>제{index + 1}조</span>
                  <h2>{section.title}</h2>
                </div>
                {section.paragraphs?.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
                {section.items?.length ? (
                  <ul>{section.items.map((item) => <li key={item}>{item}</li>)}</ul>
                ) : null}
                {section.table ? (
                  <div className="info-document-table-wrap">
                    <table>
                      <thead><tr>{section.table.headers.map((header) => <th key={header}>{header}</th>)}</tr></thead>
                      <tbody>
                        {section.table.rows.map((row) => (
                          <tr key={row.join('-')}>{row.map((cell, cellIndex) => <td key={`${cell}-${cellIndex}`}>{cell}</td>)}</tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </section>
            ))}
          </article>
        </div>
      ) : items.length > 0 ? (
        <ul className="info-page-list">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

export default InfoPage
