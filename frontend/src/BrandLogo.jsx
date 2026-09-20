import React, { useState } from 'react'

// Official brand marks via Simple Icons CDN, tinted to each brand's colour.
// [slug, hexColour]. If a slug ever fails to load, we fall back to a monogram
// so the UI never shows a broken image.
const LOGOS = {
  shopify: ['shopify', '95BF47'],
  meta_ads: ['meta', '0866FF'],
  ga4: ['googleanalytics', 'E37400'],
  clarity: ['microsoftclarity', '3A3AF0'],
  google_ads: ['googleads', '4285F4'],
  search_console: ['googlesearchconsole', '458CF5'],
}

export default function BrandLogo({ provider, size = 22, fallback = '?' }) {
  const [failed, setFailed] = useState(false)
  const spec = LOGOS[provider]

  if (!spec || failed) {
    return <span className="blogo-fallback">{(fallback || '?').slice(0, 1).toUpperCase()}</span>
  }
  const [slug, hex] = spec
  return (
    <img
      className="blogo"
      width={size}
      height={size}
      alt=""
      src={`https://cdn.simpleicons.org/${slug}/${hex}`}
      onError={() => setFailed(true)}
    />
  )
}
