import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'json-summary'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/**/*.dom.test.{ts,tsx}',
        'src/main.tsx',
        'src/components/RichTextEditor.tsx',
        'src/components/FloatingImage.tsx',
        'src/editorExtensions.ts',
        'src/components/EditorFindReplace.tsx',
        'src/components/EditorToolbar.tsx',
        'src/components/EditorToolbarControls.tsx',
        'src/components/EditorWordCount.tsx',
      ],
      thresholds: {
        lines: 70,
        branches: 69,
        functions: 70,
        statements: 70,
      },
    },
    projects: [
      {
        test: {
          name: 'node',
          globals: true,
          environment: 'node',
          include: ['src/**/*.test.{ts,tsx}'],
          exclude: ['src/**/*.dom.test.{ts,tsx}'],
        },
      },
      {
        plugins: [react()],
        test: {
          name: 'jsdom',
          globals: true,
          environment: 'jsdom',
          include: ['src/**/*.dom.test.{ts,tsx}'],
        },
      },
    ],
  },
});
