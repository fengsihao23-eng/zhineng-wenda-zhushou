/**
 * 统一的错误展示组件
 */
import React from 'react'
import { errorMessage } from '../services/http'
import './ErrorDisplay.css'

export interface ErrorDisplayProps {
  error: Error | string | null
  title?: string
  onRetry?: () => void
  onDismiss?: () => void
  variant?: 'inline' | 'banner' | 'modal'
}

export function ErrorDisplay({
  error,
  title = '操作失败',
  onRetry,
  onDismiss,
  variant = 'inline',
}: ErrorDisplayProps) {
  if (!error) return null

  const message = errorMessage(error)
  const className = `error-display error-display--${variant}`

  return (
    <div className={className} role="alert">
      <div className="error-display__icon">⚠️</div>
      <div className="error-display__content">
        <h3 className="error-display__title">{title}</h3>
        <p className="error-display__message">{message}</p>
      </div>
      <div className="error-display__actions">
        {onRetry && (
          <button
            className="error-display__button error-display__button--primary"
            onClick={onRetry}
          >
            重试
          </button>
        )}
        {onDismiss && (
          <button
            className="error-display__button error-display__button--secondary"
            onClick={onDismiss}
          >
            关闭
          </button>
        )}
      </div>
    </div>
  )
}

interface BoundaryProps {
  children: React.ReactNode
  fallback?: (error: Error, reset: () => void) => React.ReactNode
}

interface BoundaryState {
  error: Error | null
}

export class ErrorBoundary extends React.Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error }
  }

  private reset = () => this.setState({ error: null })

  render(): React.ReactNode {
    if (this.state.error) {
      return this.props.fallback?.(this.state.error, this.reset) || (
        <ErrorDisplay error="页面暂时无法显示，请重试" title="页面出错" onRetry={this.reset} />
      )
    }
    return this.props.children
  }
}
