import { expect, test } from '@playwright/test'
import { completedTaskId, resetDemoData } from './helpers.js'

test('Agent3 页面展示五类统计、Claim 和修订建议', async ({ page }) => {
  await resetDemoData(page, `/#/tasks/${completedTaskId}/evidence`)

  await expect(page.getByRole('heading', { name: '证据可信校验', exact: true }).first()).toBeVisible()
  await expect(page.locator('.verification-counts > div')).toHaveCount(5)
  await expect(page.locator('.claim-cards article')).toHaveCount(3)
  await expect(page.getByText('2 条风险描述已被拦截')).toBeVisible()
  await expect(page.getByText('修订建议')).toBeVisible()
  await expect(page.getByText('历史模型版本：Agent4-V4')).toBeVisible()
  await expect(page.getByText('Agent1 损伤量化结果')).toBeVisible()
  await expect(page.locator('.verified-package')).toContainText('已排除')

  await page.getByRole('button', { name: '只看风险 2' }).click()
  await expect(page.locator('.claim-cards article')).toHaveCount(2)
  await expect(page.getByRole('link', { name: '查看报告' })).toBeVisible()
})
