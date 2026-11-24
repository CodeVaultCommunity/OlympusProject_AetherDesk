import { expect, test } from '@playwright/test';
import axe from 'axe-core';
import { mkdir } from 'node:fs/promises';

test('IA divulga dados, envia chat e aprova somente ação exata', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 700 });
  await page.goto('/src/apps/ai/fixture.html');
  await page.getByRole('button', { name: 'Conversa de teste' }).click();
  await page.getByRole('textbox', { name: 'Mensagem' }).fill('olá');
  await page.getByRole('button', { name: 'Enviar' }).click();
  await expect(page.getByRole('status')).toContainText('aceite o envio');
  await page.getByRole('checkbox', { name: /Aceito enviar/ }).check();
  await page.getByRole('button', { name: 'Enviar' }).click();
  await expect(page.getByText('Resposta parcial')).toBeVisible();
  await expect(page.getByRole('status')).toContainText('Resposta concluída');
  await page.getByRole('button', { name: 'Ferramentas' }).click();
  await page.getByRole('button', { name: 'Revisar ação' }).click();
  await expect(page.getByRole('alertdialog')).toContainText('Servidor externo third-party · versão 4');
  await expect(page.getByRole('alertdialog')).toContainText('Destruição');
  await expect(page.getByRole('alertdialog').getByRole('button', { name: 'Negar' })).toBeFocused();
  await mkdir('.tmp/w004-captures', { recursive: true });
  await page.screenshot({ path: `.tmp/w004-captures/ai-approval-${testInfo.project.name}.png`, fullPage: true });
  await page.getByRole('button', { name: 'Solicitar ticket' }).click();
  await page.getByRole('button', { name: 'Aprovar esta ação' }).click();
  await expect(page.getByRole('status')).toContainText('concluída');
  await page.addScriptTag({ content: axe.source });
  const violations = await page.evaluate(async () => {
    const result = await (window as typeof window & { axe: typeof axe }).axe.run(document,
      { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } });
    return result.violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => node.html) }));
  });
  expect(violations).toEqual([]);
  await mkdir('.tmp/w004-captures', { recursive: true });
  await page.screenshot({ path: `.tmp/w004-captures/ai-${testInfo.project.name}.png`, fullPage: true });
});

for (const mode of ['mismatch', 'revoked'] as const) test(`IA bloqueia ${mode} sem invocar tool`, async ({ page }) => {
  await page.goto(`/src/apps/ai/fixture.html?mode=${mode}`);
  await page.getByRole('button', { name: 'Ferramentas' }).click();
  await page.getByRole('button', { name: 'Revisar ação' }).click();
  await page.getByRole('button', { name: 'Solicitar ticket' }).click();
  if (mode === 'mismatch') {
    await expect(page.getByRole('status')).toContainText('argumentos ou a versão mudaram');
    await expect(page.getByRole('button', { name: 'Aprovar esta ação' })).toHaveCount(0);
  } else {
    await page.getByRole('button', { name: 'Aprovar esta ação' }).click();
    await expect(page.getByRole('status')).toContainText('sessão foi revogada');
  }
});

test('IA sem capacidade não mostra chat nem tools', async ({ page }) => {
  await page.goto('/src/apps/ai/fixture.html?mode=forbidden');
  await expect(page.getByRole('alert')).toHaveText('Sem permissão para usar IA.');
  await expect(page.getByRole('button')).toHaveCount(0);
});
