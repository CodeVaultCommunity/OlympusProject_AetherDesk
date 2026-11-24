import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';

export default tseslint.config(
  { ignores: ['dist/**'] },
  ...tseslint.configs.recommended,
  { files: ['src/**/*.{ts,tsx}'], ...reactHooks.configs.flat.recommended,
    rules: { ...reactHooks.configs.flat.recommended.rules,
      'react-hooks/set-state-in-effect': 'warn' } },
);
