import { defineConfig } from 'vite';

// Monaco é carregado sob demanda; antecipar a otimização evita um reload HMR
// na primeira abertura do editor durante o desenvolvimento e os testes E2E.
export default defineConfig({
  server: { watch: { ignored: ['**/.tmp/**'] } },
  optimizeDeps: {
    // Evitar descoberta tardia durante os E2E: uma nova otimização recarrega
    // as páginas de todos os workers e descarta o estado do editor.
    noDiscovery: true,
    include: [
      'react', 'react/jsx-dev-runtime', 'react-dom', 'react-dom/client',
      '@monaco-editor/react', '@xterm/xterm', '@xterm/addon-fit',
      'monaco-editor/editor/editor.api',
      'monaco-editor/editor/contrib/find/browser/findController',
      'monaco-editor/language/typescript/monaco.contribution',
      'monaco-editor/language/json/monaco.contribution',
      'monaco-editor/language/css/monaco.contribution',
      'monaco-editor/language/html/monaco.contribution',
      'monaco-editor/languages/definitions/typescript/register',
      'monaco-editor/languages/definitions/javascript/register',
      'monaco-editor/languages/definitions/css/register',
      'monaco-editor/languages/definitions/html/register',
      'monaco-editor/languages/definitions/python/register',
      'monaco-editor/languages/definitions/markdown/register',
      'monaco-editor/languages/definitions/shell/register',
    ],
  },
});
