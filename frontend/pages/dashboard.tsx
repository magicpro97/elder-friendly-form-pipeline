import React, { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

const COLORS = ['#667eea', '#764ba2', '#f093fb', '#4facfe', '#00f2fe', '#43e97b', '#fa709a', '#fee140', '#30cfd0', '#330867']

export default function Dashboard() {
  const router = useRouter()
  const [overview, setOverview] = useState<any>(null)
  const [timeseries, setTimeseries] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [overviewRes, timeseriesRes] = await Promise.all([
        axios.get(`${API_BASE}/gold/overview`),
        axios.get(`${API_BASE}/gold/timeseries?days=7`)
      ])
      setOverview(overviewRes.data)
      setTimeseries(timeseriesRes.data)
    } catch (error) {
      console.error('Error loading dashboard data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await axios.post(`${API_BASE}/gold/refresh`)
      await loadData()
    } catch (error) {
      console.error('Error refreshing data:', error)
    } finally {
      setRefreshing(false)
    }
  }

  const styles = {
    container: {
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      padding: '2rem',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    },
    card: {
      maxWidth: '1400px',
      margin: '0 auto',
      background: 'white',
      borderRadius: '24px',
      boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
      overflow: 'hidden',
    },
    header: {
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      color: 'white',
      padding: '2rem',
      display: 'flex',
      justifyContent: 'space-between' as const,
      alignItems: 'center' as const,
    },
    title: {
      fontSize: '2rem',
      fontWeight: 'bold',
      margin: 0,
    },
    button: {
      background: 'rgba(255,255,255,0.2)',
      border: 'none',
      color: 'white',
      borderRadius: '12px',
      padding: '0.75rem 1.5rem',
      cursor: 'pointer',
      fontSize: '1rem',
      fontWeight: '500',
      transition: 'all 0.2s',
    },
    content: {
      padding: '2rem',
    },
    statsGrid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
      gap: '1.5rem',
      marginBottom: '2rem',
    },
    statCard: {
      background: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
      borderRadius: '16px',
      padding: '1.5rem',
      textAlign: 'center' as const,
    },
    statValue: {
      fontSize: '2rem',
      fontWeight: 'bold',
      color: '#667eea',
      margin: '0.5rem 0',
    },
    statLabel: {
      fontSize: '0.9rem',
      color: '#666',
      textTransform: 'uppercase' as const,
      letterSpacing: '1px',
    },
    chartContainer: {
      marginBottom: '2rem',
      padding: '1.5rem',
      background: '#f8f9fa',
      borderRadius: '16px',
    },
    chartTitle: {
      fontSize: '1.3rem',
      fontWeight: '600',
      marginBottom: '1rem',
      color: '#333',
    },
    loading: {
      textAlign: 'center' as const,
      padding: '3rem',
      color: '#666',
      fontSize: '1.1rem',
    },
    table: {
      width: '100%',
      borderCollapse: 'collapse' as const,
      marginTop: '1rem',
    },
    tableHeader: {
      background: '#667eea',
      color: 'white',
      padding: '1rem',
      textAlign: 'left' as const,
      fontWeight: '600',
    },
    tableRow: {
      borderBottom: '1px solid #e9ecef',
    },
    tableCell: {
      padding: '1rem',
      color: '#333',
    },
  }

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <div style={styles.loading}>Đang tải dữ liệu dashboard...</div>
        </div>
      </div>
    )
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.header}>
          <h1 style={styles.title}>📊 Gold Layer Dashboard</h1>
          <div style={{ display: 'flex', gap: '1rem' }}>
            <button
              style={styles.button}
              onClick={() => router.push('/')}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(255,255,255,0.3)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'rgba(255,255,255,0.2)'
              }}
            >
              ← Về trang chủ
            </button>
            <button
              style={styles.button}
              onClick={handleRefresh}
              disabled={refreshing}
              onMouseEnter={(e) => {
                if (!refreshing) {
                  e.currentTarget.style.background = 'rgba(255,255,255,0.3)'
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'rgba(255,255,255,0.2)'
              }}
            >
              {refreshing ? '⏳ Đang làm mới...' : '🔄 Làm mới dữ liệu'}
            </button>
          </div>
        </div>

        <div style={styles.content}>
          {/* Overall Statistics */}
          {overview?.overall && (
            <div style={styles.statsGrid}>
              <div style={styles.statCard}>
                <div style={styles.statLabel}>Tổng số biểu mẫu</div>
                <div style={styles.statValue}>{overview.overall.total_forms}</div>
              </div>
              <div style={styles.statCard}>
                <div style={styles.statLabel}>Tổng số phiên</div>
                <div style={styles.statValue}>{overview.overall.total_sessions}</div>
              </div>
              <div style={styles.statCard}>
                <div style={styles.statLabel}>Phiên hoàn thành</div>
                <div style={styles.statValue}>{overview.overall.total_completed_sessions}</div>
              </div>
              <div style={styles.statCard}>
                <div style={styles.statLabel}>Tỷ lệ hoàn thành</div>
                <div style={styles.statValue}>{overview.overall.overall_completion_rate}%</div>
              </div>
            </div>
          )}

          {/* Time Series Chart */}
          {timeseries?.daily_sessions && timeseries.daily_sessions.length > 0 && (
            <div style={styles.chartContainer}>
              <h2 style={styles.chartTitle}>📈 Xu hướng phiên theo thời gian (7 ngày)</h2>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={timeseries.daily_sessions}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="sessions" stroke="#667eea" strokeWidth={2} name="Số phiên" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Top Forms Chart */}
          {overview?.top_forms && overview.top_forms.length > 0 && (
            <div style={styles.chartContainer}>
              <h2 style={styles.chartTitle}>🏆 Top 10 biểu mẫu phổ biến</h2>
              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={overview.top_forms.slice(0, 10)}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="form_title" angle={-45} textAnchor="end" height={100} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="statistics.total_sessions" fill="#667eea" name="Tổng phiên" />
                  <Bar dataKey="statistics.completed_sessions" fill="#764ba2" name="Phiên hoàn thành" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Top Fields Chart */}
          {overview?.top_fields && overview.top_fields.length > 0 && (
            <div style={styles.chartContainer}>
              <h2 style={styles.chartTitle}>📋 Top 10 trường phổ biến</h2>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={overview.top_fields.slice(0, 10)}
                    dataKey="count"
                    nameKey="label"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label
                  >
                    {overview.top_fields.slice(0, 10).map((entry: any, index: number) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Forms Table */}
          {overview?.top_forms && overview.top_forms.length > 0 && (
            <div style={styles.chartContainer}>
              <h2 style={styles.chartTitle}>📊 Chi tiết biểu mẫu</h2>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.tableHeader}>Biểu mẫu</th>
                    <th style={styles.tableHeader}>Tổng phiên</th>
                    <th style={styles.tableHeader}>Hoàn thành</th>
                    <th style={styles.tableHeader}>Tỷ lệ (%)</th>
                    <th style={styles.tableHeader}>Tổng câu trả lời</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.top_forms.map((form: any, idx: number) => (
                    <tr key={idx} style={styles.tableRow}>
                      <td style={styles.tableCell}>
                        <a
                          href={`/forms/${encodeURIComponent(form.form_id)}`}
                          style={{ color: '#667eea', textDecoration: 'none' }}
                        >
                          {form.form_title}
                        </a>
                      </td>
                      <td style={styles.tableCell}>{form.statistics.total_sessions}</td>
                      <td style={styles.tableCell}>{form.statistics.completed_sessions}</td>
                      <td style={styles.tableCell}>{form.statistics.completion_rate}%</td>
                      <td style={styles.tableCell}>{form.statistics.total_answers}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Field Popularity by Form */}
          {overview?.top_forms && overview.top_forms.length > 0 && (
            <div style={styles.chartContainer}>
              <h2 style={styles.chartTitle}>📊 Độ phổ biến trường theo biểu mẫu</h2>
              {overview.top_forms.slice(0, 5).map((form: any, formIdx: number) => (
                <div key={formIdx} style={{ marginBottom: '2rem' }}>
                  <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: '#667eea' }}>
                    {form.form_title}
                  </h3>
                  {form.field_popularity && form.field_popularity.length > 0 && (
                    <ResponsiveContainer width="100%" height={250}>
                      <BarChart data={form.field_popularity.slice(0, 5)}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="label" angle={-45} textAnchor="end" height={80} />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Bar dataKey="answer_count" fill={COLORS[formIdx % COLORS.length]} name="Số câu trả lời" />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

