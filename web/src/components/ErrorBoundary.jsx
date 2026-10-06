import React from 'react'

// A failure inside one module must never blank the whole application: show a recoverable message instead.
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error) {
    console.error('Module render failure:', error)
  }

  componentDidUpdate(prev) {
    if (this.state.failed && prev.resetKey !== this.props.resetKey) this.setState({ failed: false })
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div role="alert" className="m-6 rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-900 space-y-2">
        <div className="font-bold">This screen could not be displayed.</div>
        <p>Something unexpected happened while showing this module. Your data is safe. Try again, or open another module from the menu.</p>
        <button type="button" onClick={() => this.setState({ failed: false })} className="px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-semibold">
          Try again
        </button>
      </div>
    )
  }
}
