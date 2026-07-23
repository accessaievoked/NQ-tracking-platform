import React from 'react'

const NAV = [
  { id: 'chats', icon: 'chat_bubble', label: 'Chats' },
  { id: 'insights', icon: 'bar_chart', label: 'Insights & Reports' },
  { id: 'workflows', icon: 'automation', label: 'Workflows' },
  { id: 'library', icon: 'storefront', label: 'Brand Library' },
]

export default function Sidebar({ page, setPage, me, onLogout }) {
  const displayName = me.name || (me.email || '').split('@')[0]
  const initials = (displayName || 'NQ').slice(0, 2).toUpperCase()
  return (
    <aside className="sidebar">
      <div className="side-logo"><span className="logo">N Q</span></div>
      <button className="newchat">
        <span className="ms">add</span><span className="lbl">Start a New Chat</span>
      </button>
      <nav className="nav">
        {NAV.map((n) => (
          <a
            key={n.id} href="#"
            className={page === n.id ? 'active' : ''}
            onClick={(e) => { e.preventDefault(); setPage(n.id) }}
          >
            <span className="ms">{n.icon}</span><span className="lbl">{n.label}</span>
          </a>
        ))}
      </nav>
      <div className="search-conv pill-input">
        <span className="ms" style={{ color: 'var(--t40)' }}>search</span>
        <input placeholder="Search Conversations" />
      </div>
      <div className="side-foot">
        <div className="avatar">{initials}</div>
        <div className="name">{displayName}</div>
        <button className="lnk logout" onClick={onLogout} title="Log out">
          <span className="ms">logout</span>
        </button>
      </div>
    </aside>
  )
}
