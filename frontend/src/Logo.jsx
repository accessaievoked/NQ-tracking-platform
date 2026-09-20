import React, { useState } from 'react'

// Brand logo. Loads the real asset from public/nq-logo.png; if that file isn't
// present yet, it falls back to a crisp inline "nq" wordmark so nothing breaks.
export default function Logo({ className = 'logo' }) {
  const [failed, setFailed] = useState(false)

  if (!failed) {
    return (
      <img
        className={className}
        src="/nq-logo.png"
        alt="nq"
        onError={() => setFailed(true)}
      />
    )
  }
  return (
    <svg className={className} viewBox="0 0 62 34" role="img" aria-label="nq">
      <text
        x="0" y="27"
        fontFamily="'Public Sans', sans-serif"
        fontSize="34" fontWeight="700" letterSpacing="-2.5"
        fill="#0f1115"
      >
        nq
      </text>
    </svg>
  )
}
