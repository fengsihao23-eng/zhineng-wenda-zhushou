import { useState } from 'react'
import { Link } from 'react-router-dom'
import { LineChart, Line, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts'
import { AppShell } from '../layouts/AppShell'
import { useStudentDashboard, useStudentTrends, type DashboardData, type TrendData } from '../hooks/useApi'
import { ErrorDisplay } from '../components/ErrorDisplay'
import './Profile.css'

function percentageOf(score: number, fullScore: number | null | undefined): number | null {
  if (!Number.isFinite(score) || fullScore == null || !Number.isFinite(fullScore) || fullScore <= 0) return null
  return (score / fullScore) * 100
}

function formatPercentage(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(1)}%`
}

function LoadingState() {
  return (
    <div className="profile-loading">
      <div className="spinner" />
      <p>正在加载你的成绩数据...</p>
    </div>
  )
}

function ScoreCard({ exam }: { exam: DashboardData['latest_exam'] }) {
  if (!exam) {
    return (
      <div className="score-card score-card--empty">
        <h3>最近考试成绩</h3>
        <p className="empty-hint">暂无考试记录</p>
      </div>
    )
  }

  const scorePercentage = percentageOf(exam.total_score, exam.full_score)
  const hasDelta = exam.score_delta !== null

  return (
    <div className="score-card">
      <div className="score-card__header">
        <h3>最近考试成绩</h3>
        <span className="score-card__date">{exam.date || '—'}</span>
      </div>
      <div className="score-card__body">
        <div className="score-display">
          <div className="score-number">
            {exam.total_score}
            <span className="score-total">/ {scorePercentage == null ? '—' : exam.full_score}</span>
          </div>
          <div className="score-percentage">{formatPercentage(scorePercentage)}</div>
        </div>
        {hasDelta && (
          <div className={`score-delta ${exam.score_delta! >= 0 ? 'positive' : 'negative'}`}>
            <span className="delta-icon">{exam.score_delta! >= 0 ? '↗' : '↘'}</span>
            <span className="delta-value">
              {exam.score_delta! >= 0 ? '+' : ''}{exam.score_delta}
            </span>
            <span className="delta-label">较上次</span>
          </div>
        )}
      </div>
      <div className="score-card__footer">
        <div className="rank-item">
          <span className="rank-label">班级排名</span>
          <span className="rank-value">{exam.class_rank ? `第 ${exam.class_rank} 名` : '—'}</span>
        </div>
        <div className="rank-item">
          <span className="rank-label">年级排名</span>
          <span className="rank-value">{exam.grade_rank ? `第 ${exam.grade_rank} 名` : '—'}</span>
        </div>
      </div>
      <div className="score-card__exam-name">{exam.name}</div>
    </div>
  )
}

function TrendChart({ trends }: { trends: TrendData }) {
  const [chartWidth, setChartWidth] = useState(0)
  const compact = chartWidth < 360
  if (!trends.exams.length) {
    return (
      <div className="trend-chart trend-chart--empty">
        <h3>成绩趋势</h3>
        <p className="empty-hint">暂无考试记录</p>
      </div>
    )
  }

  const chartData = trends.exams.map((exam) => ({
    name: exam.name,
    score: exam.score,
    fullScore: exam.full_score,
    percentage: percentageOf(exam.score, exam.full_score),
    classRank: exam.class_rank,
    gradeRank: exam.grade_rank,
  }))

  return (
    <div className="trend-chart">
      <div className="trend-chart__header">
        <h3>成绩趋势</h3>
        <span className="trend-chart__count">{trends.exams.length} 次考试</span>
      </div>
      <ResponsiveContainer width="100%" height={300} minWidth={0} onResize={setChartWidth}>
        <LineChart data={chartData} margin={{ top: 8, right: 0, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="name"
            stroke="#6b7280"
            style={{ fontSize: '12px' }}
            tickFormatter={(name: string) => compact
              ? name.match(/第\s*\d+\s*次/)?.[0] ?? (name.length > 5 ? `${name.slice(0, 5)}…` : name)
              : name.length > 8 ? `${name.slice(0, 8)}…` : name}
          />
          <YAxis
            yAxisId="score"
            width={compact ? 32 : 48}
            stroke="#6b7280"
            style={{ fontSize: '12px' }}
          />
          <YAxis
            yAxisId="percentage"
            width={compact ? 38 : 50}
            orientation="right"
            domain={[0, 100]}
            unit="%"
            stroke="#10b981"
            style={{ fontSize: '12px' }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#fff',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              padding: '12px',
            }}
            formatter={(value: unknown, name: unknown) => {
              const numValue = typeof value === 'number' ? value : null
              const strName = String(name)
              if (strName === 'score') return [numValue ?? '—', '得分']
              if (strName === 'percentage') return [numValue == null ? '—' : `${numValue.toFixed(1)}%`, '得分率']
              return [numValue ?? '—', strName]
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: '14px' }}
            formatter={(value) => {
              if (value === 'score') return '总分'
              if (value === 'percentage') return '得分率 (%)'
              return value
            }}
          />
          <Line
            yAxisId="score"
            isAnimationActive={false}
            type="monotone"
            dataKey="score"
            stroke="#3b82f6"
            strokeWidth={3}
            dot={{ fill: '#3b82f6', r: 5 }}
            activeDot={{ r: 7 }}
          />
          <Line
            yAxisId="percentage"
            isAnimationActive={false}
            type="monotone"
            dataKey="percentage"
            stroke="#10b981"
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={{ fill: '#10b981', r: 4 }}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function SubjectRadar({ subjects }: { subjects: DashboardData['subjects'] }) {
  if (!subjects.length) {
    return (
      <div className="subject-radar subject-radar--empty">
        <h3>学科雷达图</h3>
        <p className="empty-hint">暂无科目数据</p>
      </div>
    )
  }

  const radarData = subjects.map((subject) => ({
    subject: subject.name,
    percentage: percentageOf(subject.score, subject.full_score),
    fullMark: 100,
  })).filter((subject) => subject.percentage !== null)

  return (
    <div className="subject-radar">
      <div className="subject-radar__header">
        <h3>学科雷达图</h3>
        <span className="subject-radar__count">{subjects.length} 个科目</span>
      </div>
      {radarData.length > 0 ? <ResponsiveContainer width="100%" height={300} minWidth={0}>
        <RadarChart data={radarData} outerRadius="65%">
          <PolarGrid stroke="#e5e7eb" />
          <PolarAngleAxis
            dataKey="subject"
            tick={{ fontSize: 13, fill: '#374151' }}
          />
          <PolarRadiusAxis
            angle={30}
            domain={[0, 100]}
            ticks={[0, 50, 100]}
            axisLine={false}
            tick={{ fontSize: 10, fill: '#6b7280' }}
          />
          <Radar
            isAnimationActive={false}
            name="得分率"
            dataKey="percentage"
            stroke="#8b5cf6"
            fill="#8b5cf6"
            fillOpacity={0.35}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#fff',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              padding: '8px 12px',
            }}
            formatter={(value: unknown) => {
              const numValue = typeof value === 'number' ? value : null
              return [formatPercentage(numValue), '得分率']
            }}
          />
        </RadarChart>
      </ResponsiveContainer> : <p className="empty-hint">科目满分待补充，暂无法计算得分率</p>}
      {radarData.length > 0 && radarData.length < subjects.length && <p className="empty-hint">雷达图仅包含满分已知的科目</p>}
      <div className="subject-list">
        {subjects.map((subject) => (
          <div key={subject.name} className="subject-item">
            <div className="subject-item__header">
              <span className="subject-name">{subject.name}</span>
              <span className="subject-score">
                {subject.score} / {percentageOf(subject.score, subject.full_score) == null ? '—' : subject.full_score}
              </span>
            </div>
            <div className="subject-item__progress">
              <div
                className="progress-bar"
                style={{ width: `${Math.min(100, Math.max(0, percentageOf(subject.score, subject.full_score) ?? 0))}%` }}
              />
            </div>
            <div className="subject-item__meta">
              <span>{formatPercentage(percentageOf(subject.score, subject.full_score))}</span>
              <span>班级第 {subject.class_rank || '—'} 名</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ProfilePage() {
  const {
    data: dashboardData,
    isLoading: isDashboardLoading,
    error: dashboardError,
    refetch: refetchDashboard,
  } = useStudentDashboard()

  const {
    data: trendsData,
    isLoading: isTrendsLoading,
    error: trendsError,
    refetch: refetchTrends,
  } = useStudentTrends()

  const isLoading = isDashboardLoading || isTrendsLoading
  const error = dashboardError || trendsError

  const handleRetry = () => {
    void refetchDashboard()
    void refetchTrends()
  }

  if (isLoading) {
    return (
      <AppShell title="成绩概览" eyebrow="学生空间 / 成绩概览">
        <LoadingState />
      </AppShell>
    )
  }

  if (error) {
    return (
      <AppShell title="成绩概览" eyebrow="学生空间 / 成绩概览">
        <ErrorDisplay
          error={error}
          title="数据加载失败"
          onRetry={handleRetry}
        />
      </AppShell>
    )
  }

  if (!dashboardData || !trendsData) {
    return (
      <AppShell title="成绩概览" eyebrow="学生空间 / 成绩概览">
        <div className="profile-empty">
          <div className="empty-icon">📊</div>
          <h3>暂无成绩数据</h3>
          <p>完成考试或导入成绩后，这里会自动展示你的成绩分析</p>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell
      title={`${dashboardData.student.name || '同学'}的成绩概览`}
      eyebrow="学生空间 / 成绩概览"
    >
      <div className="profile-container">
        <div className="profile-header">
          <div>
            <h1>{dashboardData.student.name}</h1>
            <p className="profile-subtitle">
              已记录 {dashboardData.exam_count} 次考试
            </p>
          </div>
          <div className="profile-actions">
            <Link to="/trends" className="secondary-button">
              查看详细趋势 →
            </Link>
            <Link to="/chat" className="primary-button">
              问问学习助手
            </Link>
          </div>
        </div>

        <div className="profile-grid">
          <div className="profile-grid__main">
            <ScoreCard exam={dashboardData.latest_exam} />
            <TrendChart trends={trendsData} />
          </div>
          <div className="profile-grid__sidebar">
            <SubjectRadar subjects={dashboardData.subjects} />
          </div>
        </div>

        <div className="profile-footer">
          <div className="data-freshness">
            <span className="status-dot status-dot--active" />
            <span>数据已同步</span>
            <span className="data-freshness__time">
              最后更新：{dashboardData.latest_exam?.date || '—'}
            </span>
          </div>
        </div>
      </div>
    </AppShell>
  )
}
