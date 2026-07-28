import React from "react";

type State = { failed: boolean };

class AppErrorBoundary extends React.Component<React.PropsWithChildren, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error): void {
    console.error("The application could not render", error);
  }

  render(): React.ReactNode {
    if (!this.state.failed) return this.props.children;

    return (
      <main>
        <div className="page" role="alert">
          <h1>This page could not load</h1>
          <p>The site may have been updated while this tab was open.</p>
          <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
            Reload page
          </button>
        </div>
      </main>
    );
  }
}

export default AppErrorBoundary;
