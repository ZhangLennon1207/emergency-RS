import { expect, test } from '@playwright/test'
import { resetDemoData } from './helpers.js'

test('任务列表支持关键词和状态筛选', async ({ page }) => {
  await resetDemoData(page, '/#/tasks')

  await expect(page.locator('.task-table-row')).toHaveCount(3)
  await page.getByPlaceholder('搜索任务名称、地点或编号').fill('长沙县')
  await expect(page.locator('.task-table-row')).toHaveCount(1)
  await expect(page.getByText('长沙县震后建筑损毁评估')).toBeVisible()

  await page.getByPlaceholder('搜索任务名称、地点或编号').clear()
  await page.getByLabel('执行状态').selectOption('running')
  await expect(page.locator('.task-table-row')).toHaveCount(1)
  await expect(page.getByText('浏阳市洪涝建筑影响研判')).toBeVisible()

  await page.getByRole('button', { name: '重置' }).click()
  await page.getByLabel('灾害类型').selectOption('wildfire')
  await page.getByLabel('综合风险').selectOption('high')
  await expect(page.locator('.task-table-row')).toHaveCount(1)
  await expect(page.getByText('岳阳市山火损毁快速评估')).toBeVisible()
})
