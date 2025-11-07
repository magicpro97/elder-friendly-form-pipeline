import React, { useEffect, useState, useRef } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

interface Message {
  type: 'bot' | 'user'
  text: string
  fieldId?: string
}

export default function FormChat() {
  const router = useRouter()
  const { id } = router.query
  const rawId = Array.isArray(id) ? id[0] : id
  const formId = rawId ? decodeURIComponent(rawId as string) : ''
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [question, setQuestion] = useState<any>(null)
  const [answer, setAnswer] = useState('')
  const [done, setDone] = useState(false)
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [formTitle, setFormTitle] = useState<string>('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    if (!rawId) return
    const start = async () => {
      try {
        // Get form title
        const formRes = await axios.get(`${API_BASE}/forms/${formId}`)
        setFormTitle(formRes.data.title || formId)
        
        // Start session
        const res = await axios.post(`${API_BASE}/sessions`, { formId })
        setSessionId(res.data.sessionId)
        
        // Get first question
        const nq = await axios.post(`${API_BASE}/sessions/${res.data.sessionId}/next-question`, {})
        setQuestion(nq.data.nextQuestion)
        setDone(nq.data.done)
        
        // Add welcome message
        if (nq.data.nextQuestion) {
          setMessages([{
            type: 'bot',
            text: `Xin chào! Tôi sẽ giúp bạn điền biểu mẫu "${formRes.data.title || formId}". Hãy trả lời các câu hỏi sau:`,
          }, {
            type: 'bot',
            text: nq.data.nextQuestion.text,
            fieldId: nq.data.nextQuestion.id,
          }])
        }
      } catch (error) {
        console.error('Error starting session:', error)
        setMessages([{
          type: 'bot',
          text: 'Có lỗi xảy ra khi khởi tạo phiên làm việc. Vui lòng thử lại.',
        }])
      }
    }
    start()
  }, [id])

  const submitAnswer = async () => {
    if (!sessionId || !answer.trim() || !question) return
    
    const userAnswer = answer.trim()
    setAnswer('')
    setLoading(true)
    
    // Add user message
    const newMessages = [...messages, { type: 'user' as const, text: userAnswer }]
    setMessages(newMessages)
    
    try {
      const nq = await axios.post(`${API_BASE}/sessions/${sessionId}/next-question`, {
        lastAnswer: { fieldId: question.id, value: userAnswer }
      })
      
      setQuestion(nq.data.nextQuestion)
      setDone(nq.data.done)
      
      if (nq.data.done) {
        setMessages([...newMessages, {
          type: 'bot',
          text: 'Cảm ơn bạn! Bạn đã hoàn thành tất cả các câu hỏi. Bạn có muốn tải biểu mẫu đã điền không?',
        }])
      } else if (nq.data.nextQuestion) {
        setMessages([...newMessages, {
          type: 'bot',
          text: nq.data.nextQuestion.text,
          fieldId: nq.data.nextQuestion.id,
        }])
      }
    } catch (error) {
      console.error('Error submitting answer:', error)
      setMessages([...newMessages, {
        type: 'bot',
        text: 'Có lỗi xảy ra. Vui lòng thử lại.',
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const finish = async () => {
    if (!sessionId) return
    setLoading(true)
    try {
      const res = await axios.post(`${API_BASE}/sessions/${sessionId}/fill`, { answers: {} }, { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      setPdfUrl(url)
      setMessages([...messages, {
        type: 'bot',
        text: 'Biểu mẫu đã được tạo thành công! Bạn có thể tải xuống ngay bây giờ.',
      }])
    } catch (error) {
      console.error('Error generating PDF:', error)
      setMessages([...messages, {
        type: 'bot',
        text: 'Có lỗi xảy ra khi tạo biểu mẫu. Vui lòng thử lại.',
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!loading && !done) {
        submitAnswer()
      }
    }
  }

  const styles = {
    container: {
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      padding: '1rem',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    },
    chatContainer: {
      maxWidth: '900px',
      margin: '0 auto',
      height: 'calc(100vh - 2rem)',
      display: 'flex',
      flexDirection: 'column' as const,
      background: 'white',
      borderRadius: '24px',
      boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
      overflow: 'hidden',
    },
    header: {
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      color: 'white',
      padding: '1.5rem 2rem',
      display: 'flex',
      alignItems: 'center' as const,
      justifyContent: 'space-between' as const,
    },
    headerLeft: {
      display: 'flex',
      alignItems: 'center' as const,
      gap: '1rem',
    },
    backButton: {
      background: 'rgba(255,255,255,0.2)',
      border: 'none',
      color: 'white',
      borderRadius: '12px',
      padding: '0.5rem 1rem',
      cursor: 'pointer',
      fontSize: '0.9rem',
      fontWeight: '500',
      transition: 'all 0.2s',
    },
    title: {
      fontSize: '1.5rem',
      fontWeight: 'bold',
      margin: 0,
    },
    messagesContainer: {
      flex: 1,
      overflowY: 'auto' as const,
      padding: '2rem',
      background: '#f8f9fa',
    },
    message: {
      marginBottom: '1.5rem',
      display: 'flex',
      animation: 'fadeIn 0.3s ease',
    },
    messageBot: {
      justifyContent: 'flex-start' as const,
    },
    messageUser: {
      justifyContent: 'flex-end' as const,
    },
    messageBubble: {
      maxWidth: '70%',
      padding: '1rem 1.25rem',
      borderRadius: '18px',
      wordWrap: 'break-word' as const,
      lineHeight: '1.5',
    },
    messageBubbleBot: {
      background: 'white',
      color: '#333',
      borderBottomLeftRadius: '4px',
      boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
    },
    messageBubbleUser: {
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      color: 'white',
      borderBottomRightRadius: '4px',
    },
    inputContainer: {
      padding: '1.5rem 2rem',
      background: 'white',
      borderTop: '1px solid #e9ecef',
      display: 'flex',
      gap: '1rem',
      alignItems: 'center' as const,
    },
    input: {
      flex: 1,
      padding: '1rem 1.25rem',
      border: '2px solid #e9ecef',
      borderRadius: '24px',
      fontSize: '1rem',
      outline: 'none',
      transition: 'all 0.2s',
    },
    sendButton: {
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      border: 'none',
      color: 'white',
      borderRadius: '24px',
      padding: '1rem 2rem',
      cursor: 'pointer',
      fontSize: '1rem',
      fontWeight: '600',
      transition: 'all 0.2s',
      boxShadow: '0 4px 12px rgba(102, 126, 234, 0.4)',
    },
    sendButtonDisabled: {
      opacity: 0.5,
      cursor: 'not-allowed',
    },
    downloadButton: {
      background: 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)',
      border: 'none',
      color: 'white',
      borderRadius: '24px',
      padding: '1rem 2rem',
      cursor: 'pointer',
      fontSize: '1rem',
      fontWeight: '600',
      transition: 'all 0.2s',
      boxShadow: '0 4px 12px rgba(17, 153, 142, 0.4)',
      marginTop: '1rem',
    },
    downloadLink: {
      display: 'inline-block',
      background: 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)',
      color: 'white',
      borderRadius: '24px',
      padding: '1rem 2rem',
      textDecoration: 'none',
      fontSize: '1rem',
      fontWeight: '600',
      transition: 'all 0.2s',
      boxShadow: '0 4px 12px rgba(17, 153, 142, 0.4)',
      marginTop: '1rem',
    },
    loading: {
      textAlign: 'center' as const,
      color: '#666',
      padding: '1rem',
    },
  }

  return (
    <div style={styles.container}>
      <div style={styles.chatContainer}>
        <div style={styles.header}>
          <div style={styles.headerLeft}>
            <button
              style={styles.backButton}
              onClick={() => router.push('/')}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(255,255,255,0.3)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'rgba(255,255,255,0.2)'
              }}
            >
              ← Quay lại
            </button>
            <h1 style={styles.title}>🤖 {formTitle || 'FormBot Chat'}</h1>
          </div>
        </div>
        
        <div style={styles.messagesContainer}>
          {messages.map((msg, idx) => (
            <div
              key={idx}
              style={{
                ...styles.message,
                ...(msg.type === 'bot' ? styles.messageBot : styles.messageUser),
              }}
            >
              <div
                style={{
                  ...styles.messageBubble,
                  ...(msg.type === 'bot' ? styles.messageBubbleBot : styles.messageBubbleUser),
                }}
              >
                {msg.text}
              </div>
            </div>
          ))}
          {loading && (
            <div style={styles.loading}>Đang xử lý...</div>
          )}
          {done && !pdfUrl && (
            <div style={{ textAlign: 'center' as const }}>
              <button
                style={styles.downloadButton}
                onClick={finish}
                disabled={loading}
                onMouseEnter={(e) => {
                  if (!loading) {
                    e.currentTarget.style.transform = 'translateY(-2px)'
                    e.currentTarget.style.boxShadow = '0 6px 16px rgba(17, 153, 142, 0.5)'
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = ''
                  e.currentTarget.style.boxShadow = '0 4px 12px rgba(17, 153, 142, 0.4)'
                }}
              >
                {loading ? 'Đang tạo...' : '📥 Tạo biểu mẫu đã điền'}
              </button>
            </div>
          )}
          {pdfUrl && (
            <div style={{ textAlign: 'center' as const }}>
              <a
                href={pdfUrl}
                download={`${formId}-filled.pdf`}
                style={styles.downloadLink}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)'
                  e.currentTarget.style.boxShadow = '0 6px 16px rgba(17, 153, 142, 0.5)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = ''
                  e.currentTarget.style.boxShadow = '0 4px 12px rgba(17, 153, 142, 0.4)'
                }}
              >
                📥 Tải xuống PDF
              </a>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
        
        {!done && (
          <div style={styles.inputContainer}>
            <input
              ref={inputRef}
              type="text"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Nhập câu trả lời của bạn..."
              disabled={loading}
              style={styles.input}
              onFocus={(e) => {
                e.currentTarget.style.borderColor = '#667eea'
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor = '#e9ecef'
              }}
            />
            <button
              style={{
                ...styles.sendButton,
                ...(loading || !answer.trim() ? styles.sendButtonDisabled : {}),
              }}
              onClick={submitAnswer}
              disabled={loading || !answer.trim()}
              onMouseEnter={(e) => {
                if (!loading && answer.trim()) {
                  e.currentTarget.style.transform = 'translateY(-2px)'
                  e.currentTarget.style.boxShadow = '0 6px 16px rgba(102, 126, 234, 0.5)'
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = ''
                e.currentTarget.style.boxShadow = '0 4px 12px rgba(102, 126, 234, 0.4)'
              }}
            >
              {loading ? '⏳' : '📤'}
            </button>
          </div>
        )}
      </div>
      
      <style jsx global>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  )
}


