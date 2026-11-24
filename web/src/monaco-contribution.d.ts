declare module 'monaco-editor/language/typescript/monaco.contribution' {
  export function getTypeScriptWorker(): Promise<(
    uri: unknown
  ) => Promise<{ getSemanticDiagnostics(uri: string): Promise<unknown[]> }>>;
}
