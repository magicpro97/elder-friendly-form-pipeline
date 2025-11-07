import React, { useEffect, useState } from 'react'
import axios from 'axios'
import { useRouter } from 'next/router'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

export default function Home() {
  const router = useRouter()
  const [forms, setForms] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const run = async () => {
      try {
        const res = await axios.get(`${API_BASE}/forms`)
        setForms(res.data.items || [])
      } finally {
        setLoading(false)
      }
    }
    run()
  }, [])

  const styles = {
    container: {
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      padding: '2rem',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    },
    card: {
      maxWidth: '900px',
      margin: '0 auto',
      background: 'white',
      borderRadius: '24px',
      boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
      overflow: 'hidden',
    },
    header: {
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      color: 'white',
      padding: '2.5rem',
      display: 'flex',
      justifyContent: 'space-between' as const,
      alignItems: 'center' as const,
    },
    title: {
      fontSize: '2.5rem',
      fontWeight: 'bold',
      margin: '0 0 0.5rem 0',
    },
    subtitle: {
      fontSize: '1.1rem',
      opacity: 0.9,
      margin: 0,
    },
    content: {
      padding: '2rem',
    },
    loading: {
      textAlign: 'center' as const,
      padding: '3rem',
      color: '#666',
      fontSize: '1.1rem',
    },
    formGrid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
      gap: '1.5rem',
      marginTop: '1rem',
    },
    formCard: {
      background: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
      borderRadius: '16px',
      padding: '1.5rem',
      cursor: 'pointer',
      transition: 'all 0.3s ease',
      border: '2px solid transparent',
      textDecoration: 'none',
      color: '#333',
      display: 'block',
    },
    formCardHover: {
      transform: 'translateY(-4px)',
      boxShadow: '0 8px 20px rgba(0,0,0,0.15)',
      borderColor: '#667eea',
    },
    formTitle: {
      fontSize: '1.2rem',
      fontWeight: '600',
      margin: '0 0 0.5rem 0',
      color: '#1a1a1a',
    },
    formId: {
      fontSize: '0.85rem',
      color: '#666',
      fontFamily: 'monospace',
      wordBreak: 'break-all' as const,
    },
    empty: {
      textAlign: 'center' as const,
      padding: '3rem',
      color: '#999',
      fontSize: '1.1rem',
    },
  }

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <div style={styles.loading}>Đang tải danh sách biểu mẫu...</div>
        </div>
      </div>
    )
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.header}>
          <div>
            <h1 style={styles.title}>🤖 FormBot Chat</h1>
            <p style={styles.subtitle}>Chọn một biểu mẫu để bắt đầu điền thông tin</p>
          </div>
          <a
            href="/dashboard"
            style={{
              background: 'rgba(255,255,255,0.2)',
              color: 'white',
              borderRadius: '12px',
              padding: '0.75rem 1.5rem',
              textDecoration: 'none',
              fontSize: '1rem',
              fontWeight: '500',
              transition: 'all 0.2s',
              display: 'inline-block',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255,255,255,0.3)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255,255,255,0.2)'
            }}
          >
            📊 Dashboard
          </a>
        </div>
        <div style={styles.content}>
          {forms.length === 0 ? (
            <div style={styles.empty}>Chưa có biểu mẫu nào. Hãy upload file để bắt đầu!</div>
          ) : (
            <div style={styles.formGrid}>
              {forms.map((f) => (
                <a
                  key={f.id}
                  href={`/forms/${encodeURIComponent(f.id)}`}
                  style={styles.formCard}
                  onMouseEnter={(e) => {
                    Object.assign(e.currentTarget.style, styles.formCardHover)
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = ''
                    e.currentTarget.style.boxShadow = ''
                    e.currentTarget.style.borderColor = ''
                  }}
                >
                  <div style={styles.formTitle}>{f.title || 'Biểu mẫu không có tiêu đề'}</div>
                  <div style={styles.formId}>{f.id}</div>
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}


