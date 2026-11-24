import { expect, test } from '@playwright/test';
import axe from 'axe-core';
import { mkdir } from 'node:fs/promises';

test('Containers owner confirma ações, vê rollback e alcança controles em viewport estreito', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 640 });
  await page.goto('/src/apps/containers/fixture.html');
  await expect(page.getByRole('heading', { name: 'api' })).toBeVisible();
  await page.getByRole('button', { name: 'Iniciar', exact: true }).click();
  const dialog = page.getByRole('alertdialog');
  await expect(dialog).toContainText('Iniciar api');
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await page.getByRole('button', { name: 'Iniciar', exact: true }).click();
  await dialog.getByRole('button', { name: 'Confirmar' }).click();
  await expect(page.getByText('Portal · Em execução')).toBeVisible();
  await page.getByLabel('Template aprovado').selectOption('web');
  await page.getByRole('button', { name: 'Publicar' }).click();
  await expect(dialog).toContainText('reiniciar a aplicação');
  await dialog.getByRole('button', { name: 'Confirmar' }).click();
  await expect(page.getByText(/versão anterior foi restaurada/)).toBeVisible();
  await page.addScriptTag({ content: axe.source });
  const violations = await page.evaluate(async () => {
    const report = await (window as typeof window & { axe: typeof axe }).axe.run(document,
      { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } });
    return report.violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => ({ html: node.html, summary: node.failureSummary })) }));
  });
  expect(violations).toEqual([]);
  await mkdir('.tmp/w004-captures', { recursive: true });
  await page.screenshot({ path: `.tmp/w004-captures/containers-${testInfo.project.name}.png`, fullPage: true });
});

test('Containers admin control-only não recebe conteúdo privado', async ({ page }) => {
  await page.goto('/src/apps/containers/fixture.html?role=admin');
  await expect(page.getByRole('heading', { name: 'api de outra conta' })).toBeVisible();
  await expect(page.getByText(/não inclui acesso a logs/)).toBeVisible();
  await expect(page.getByText('Log privado da aplicação')).toHaveCount(0);
  await expect(page.getByText('Referência de secret')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Criar build aprovado' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Remover' }).click();
  await expect(page.getByRole('alertdialog')).toContainText('retenção configurada');
});

test('Containers sem capacidade não consulta a API nem mostra operações', async ({ page }) => {
  await page.goto('/src/apps/containers/fixture.html?role=forbidden');
  await expect(page.getByRole('alert')).toHaveText('Sem permissão para ver aplicações.');
  await expect(page.getByRole('button')).toHaveCount(0);
  await expect(page.getByText('Log privado da aplicação')).toHaveCount(0);
});
