import { expect, test } from '@playwright/test';
import axe from 'axe-core';
import { mkdir } from 'node:fs/promises';

test('IDE abre pela árvore, protege dirty, salva e mostra rollback de deploy', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 700 });
  await page.goto('/src/apps/ide/fixture.html');
  await page.getByRole('button', { name: 'main.ts', exact: true }).click();
  await page.getByRole('textbox', { name: 'Editor' }).fill('export const ready = false;');
  await expect(page.getByRole('button', { name: 'Deploy' })).toBeDisabled();
  await page.getByRole('button', { name: 'Fechar src/main.ts' }).click();
  await expect(page.getByRole('alertdialog')).toContainText('Alterações não salvas');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Salvar' }).click();
  await expect(page.getByRole('button', { name: 'Deploy' })).toBeEnabled();
  await page.getByRole('button', { name: 'Deploy' }).click();
  await expect(page.getByRole('alertdialog')).toContainText('Publicar portal');
  await page.getByRole('alertdialog').getByRole('button', { name: 'Confirmar' }).click();
  await expect(page.getByText(/release anterior restaurada/)).toBeVisible();
  await page.getByRole('button', { name: 'Terminal à direita' }).click();
  await expect(page.getByRole('button', { name: 'Terminal embaixo' })).toBeVisible();
  await page.addScriptTag({ content: axe.source });
  const violations = await page.evaluate(async () => {
    const result = await (window as typeof window & { axe: typeof axe }).axe.run(document,
      { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } });
    return result.violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => node.html) }));
  });
  expect(violations).toEqual([]);
  await mkdir('.tmp/w004-captures', { recursive: true });
  await page.screenshot({ path: `.tmp/w004-captures/ide-${testInfo.project.name}.png`, fullPage: true });
});

test('IDE recupera rascunho e explicita conflito de revisão', async ({ page }) => {
  await page.goto('/src/apps/ide/fixture.html?conflict=1');
  await page.getByRole('button', { name: 'main.ts', exact: true }).click();
  await page.getByRole('textbox', { name: 'Editor' }).fill('rascunho local');
  await page.reload();
  await page.getByRole('button', { name: 'main.ts', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Editor' })).toHaveValue('rascunho local');
  await page.getByRole('button', { name: 'Salvar' }).click();
  await expect(page.getByRole('alert')).toContainText('Conflito');
  await page.getByRole('button', { name: 'Comparar com servidor' }).click();
  await expect(page.getByRole('dialog', { name: 'Diff src/main.ts' })).toContainText('rascunho local');
});
