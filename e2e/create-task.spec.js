import { expect, test } from '@playwright/test'
import { resetDemoData } from './helpers.js'

test('填写任务信息并选择双时相影像后可以创建任务', async ({ page }) => {
  await resetDemoData(page, '/#/tasks/new')
  const validPng = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64',
  )

  const submit = page.getByRole('button', { name: /提交模拟任务/ })
  await expect(submit).toBeDisabled()
  await expect(page.getByText('提交前还需要：')).toBeVisible()

  await page.getByPlaceholder('例如：长沙县震后建筑损毁评估').fill('Playwright 功能测试任务')
  await page.getByPlaceholder('省 / 市 / 区县或坐标').fill('湖南省长沙市')

  const uploads = page.locator('input[type="file"]')
  await uploads.nth(0).setInputFiles({
    name: 'pre.png',
    mimeType: 'image/png',
    buffer: validPng,
  })
  await uploads.nth(1).setInputFiles({
    name: 'post.png',
    mimeType: 'image/png',
    buffer: validPng,
  })

  await expect(page.getByText('pre.png')).toBeVisible()
  await expect(page.getByText('post.png')).toBeVisible()
  await expect(page.getByText('输入检查已通过，可以提交任务。')).toBeVisible()
  await expect(submit).toBeEnabled()
  await submit.click()

  await expect(page).toHaveURL(/#\/tasks\/TASK-\d{8}-004$/)
  await expect(page.getByRole('heading', { name: 'Playwright 功能测试任务' })).toBeVisible()
  await expect(page.getByRole('img', { name: '灾前影像' })).toBeVisible()
  await expect(page.getByRole('img', { name: '灾后影像' })).toBeVisible()
  await expect(page.getByText('已通过尺寸一致性检查：1 × 1')).toBeVisible()
})


test('双时相影像尺寸不一致时阻止提交', async ({ page }) => {
  await resetDemoData(page, '/#/tasks/new')
  await page.getByPlaceholder('例如：长沙县震后建筑损毁评估').fill('尺寸校验任务')
  await page.getByPlaceholder('省 / 市 / 区县或坐标').fill('测试区域')

  const imageBuffers = await page.evaluate(() =>
    [1, 2].map((width) => {
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = 1
      return canvas.toDataURL('image/png').split(',')[1]
    }),
  )
  const uploads = page.locator('input[type="file"]')
  await uploads.nth(0).setInputFiles({
    name: 'pre.png',
    mimeType: 'image/png',
    buffer: Buffer.from(imageBuffers[0], 'base64'),
  })
  await uploads.nth(1).setInputFiles({
    name: 'post.png',
    mimeType: 'image/png',
    buffer: Buffer.from(imageBuffers[1], 'base64'),
  })

  await expect(page.getByText('两张影像尺寸必须一致')).toBeVisible()
  await expect(page.getByRole('button', { name: /提交模拟任务/ })).toBeDisabled()
})

test('场景编号包含非法字符时给出提示并阻止提交', async ({ page }) => {
  await resetDemoData(page, '/#/tasks/new')

  const sampleId = page.getByPlaceholder('例如：EARTHQUAKE-TURKEY-003679')
  await sampleId.fill('长沙 灾情/001')

  await expect(sampleId).toHaveAttribute('aria-invalid', 'true')
  await expect(page.getByText('修正场景编号格式')).toBeVisible()
  await expect(page.getByRole('button', { name: /提交模拟任务/ })).toBeDisabled()

  await sampleId.fill('CHANGSHA-2026_001')
  await expect(sampleId).toHaveAttribute('aria-invalid', 'false')
  await expect(page.getByText('修正场景编号格式')).toHaveCount(0)
})
