import Editor, { type OnMount } from '@monaco-editor/react';
import { monaco } from './monaco';

export function MonacoPane({ path, language, content, theme, onEditor, onSave, onChange }: {
  path: string;
  language: string;
  content: string;
  theme: 'dark' | 'light';
  onEditor: (editor: Parameters<OnMount>[0]) => void;
  onSave: () => void;
  onChange: (value: string) => void;
}) {
  const onMount: OnMount = editor => {
    onEditor(editor);
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, onSave);
  };
  return <Editor path={path} language={language} value={content}
    theme={theme === 'light' ? 'vs' : 'vs-dark'} onMount={onMount}
    onChange={value => onChange(value || '')}
    options={{ minimap: { enabled: false }, automaticLayout: true, fontSize: 13 }} />;
}
