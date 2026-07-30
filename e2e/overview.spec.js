import { expect, test } from '@playwright/test'
import { resetDemoData } from './helpers.js'

test('总览页可以进入任务中心', async ({ page }) => {
  await resetDemoData(page)

  await expect(page.getByRole('heading', { name: '多智能体研判态势总览' })).toBeVisible()
  await expect(page.getByText('Mock 演示模式').first()).toBeVisible()
  await expect(page.getByText('四智能体流程')).toHaveCount(0)
  await expect(page.locator('.hero-flow > div')).toHaveCount(4)
  await expect(page.locator('.sidebar-nav .active')).toHaveCount(1)

  await page.getByRole('link', { name: '任务中心' }).click()
  await expect(page).toHaveURL(/#\/tasks$/)
  await expect(page.getByRole('heading', { name: '研判任务中心' })).toBeVisible()
  await expect(page.locator('.sidebar-nav .active')).toHaveCount(1)
})
