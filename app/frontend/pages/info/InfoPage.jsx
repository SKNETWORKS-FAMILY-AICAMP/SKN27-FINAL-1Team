import React from 'react'

function InfoPage({ title, description, items = [] }) {
  return (
    <div className="page-container">
      <h1>{title}</h1>
      <p>{description}</p>
      {items.length > 0 && (
        <ul className="info-page-list">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default InfoPage
