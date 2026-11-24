import { Component, type ReactNode } from 'react';

type Props = { children: ReactNode; appName: string };
type State = { failed: boolean };

export class AppBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State { return { failed: true }; }

  componentDidCatch() {
    // A UI não registra conteúdo de arquivos, terminais ou sessões em logs.
  }

  render() {
    if (this.state.failed) return <div className="app-failure" role="alert">
      <strong>{this.props.appName} não pôde ser exibido.</strong>
      <button onClick={() => this.setState({ failed: false })}>Tentar novamente</button>
    </div>;
    return this.props.children;
  }
}
