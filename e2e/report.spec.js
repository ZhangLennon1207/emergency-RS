import { expect, test } from '@playwright/test'
import { completedTaskId, resetDemoData } from './helpers.js'

test('Agent4 报告包含固定章节并支持下载', async ({ page }) => {
  await resetDemoData(page, `/#/tasks/${completedTaskId}/report`)

  await expect(page.getByRole('heading', { name: '灾害损毁评估报告' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '1. 报告摘要' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '5. 证据局限与不可下结论事项' })).toBeVisible()
  await expect(page.getByText('Markdown 未完整包含')).toHaveCount(0)

  const markdownDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载 Markdown' }).click()
  await expect((await markdownDownload).suggestedFilename()).toBe(`${completedTaskId}.md`)

  const jsonDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载结构化 JSON' }).click()
  await expect((await jsonDownload).suggestedFilename()).toBe(`${completedTaskId}.json`)
})
