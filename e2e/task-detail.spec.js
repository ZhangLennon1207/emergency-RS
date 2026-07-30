import { expect, test } from '@playwright/test'
import { completedTaskId, resetDemoData } from './helpers.js'

test('任务详情明确展示失败、跳过和下游等待状态', async ({ page }) => {
  await resetDemoData(page, `/#/tasks/${completedTaskId}`)
  await page.evaluate((taskId) => {
    const key = 'emergency-rs-demo-tasks'
    const tasks = JSON.parse(window.localStorage.getItem(key))
    const task = tasks.find((item) => item.id === taskId)
    task.status = 'partial_success'
    task.agents[2] = {
      ...task.agents[2],
      status: 'failed',
      progress: 100,
      error: { message: '证据校验服务暂时不可用。' },
    }
    task.agents[3] = {
      ...task.agents[3],
      status: 'skipped',
      progress: 0,
      error: { message: '缺少 Agent3 校验结果，未生成报告。' },
    }
    window.localStorage.setItem(key, JSON.stringify(tasks))
  }, completedTaskId)
  await page.reload()

  await expect(page.locator('.agent-stage')).toHaveCount(4)
  await expect(page.getByText('证据校验服务暂时不可用。')).toBeVisible()
  await expect(page.getByText('缺少 Agent3 校验结果，未生成报告。')).toBeVisible()
  await expect(page.getByText('Agent3 等待中')).toBeVisible()
  await expect(page.getByText('Agent4 等待中')).toBeVisible()
})

test('任务成果文件支持切换、打开和下载', async ({ page }) => {
  await resetDemoData(page, `/#/tasks/${completedTaskId}`)
  const imageDataUrl = await page.evaluate(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 2
    canvas.height = 2
    return canvas.toDataURL('image/png')
  })
  await page.evaluate(({ dataUrl, taskId }) => {
    const key = 'emergency-rs-demo-tasks'
    const tasks = JSON.parse(window.localStorage.getItem(key))
    const task = tasks.find((item) => item.id === taskId)
    task.artifacts = {
      input_pre: dataUrl,
      agent1_fused_overlay: dataUrl,
    }
    window.localStorage.setItem(key, JSON.stringify(tasks))
  }, { dataUrl: imageDataUrl, taskId: completedTaskId })
  await page.reload()

  await expect(page.getByRole('heading', { name: '任务成果文件' })).toBeVisible()
  await page.getByRole('button', { name: 'Agent1 融合叠加图' }).click()
  await expect(page.getByRole('img', { name: 'Agent1 融合叠加图' })).toBeVisible()
  await expect(page.getByRole('link', { name: '打开原图' })).toHaveAttribute('target', '_blank')
  await expect(page.getByRole('link', { name: '下载' })).toHaveAttribute('download')
})
