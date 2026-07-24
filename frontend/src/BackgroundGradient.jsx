import React from 'react'

// Static center blob: a blue glow and a pink glow overlap near the middle of the
// screen and blend into a soft purple where they meet, over a white base. Styles
// live in index.css (.bg-aurora). Sits fixed behind the whole app.
export default function BackgroundGradient() {
  return (
    <div className="bg-aurora" aria-hidden="true">
      <div className="blob blue" />
      <div className="blob pink" />
    </div>
  )
}
