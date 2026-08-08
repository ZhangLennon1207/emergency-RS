import { expect, test } from '@playwright/test'

test('真实模式任务中心读取后端摘要并进入实时任务页', async ({ page }) => {
  test.skip(process.env.VITE_USE_MOCK !== 'false', '仅在真实 API 模式测试中运行')

  await page.route('http://127.0.0.1:8000/api/v1/jobs**', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      json: {
        items: [
          {
            job_id: 'job-real-001',
            sample_id: 'case-real-001',
            status: 'succeeded',
            stage: '当前双智能体范围执行成功',
            progress: 100,
            created_at: '2026-08-08T08:00:00Z',
            scope: 'agent1_agent2_local_only',
            four_agent_pipeline_complete: false,
            scene_risk_level: 'high',
            review_required: true,
          },
        ],
        page: 1,
        page_size: 100,
        total: 1,
      },
    })
  })

  await page.goto('/#/tasks')

  await expect(page.getByRole('heading', { name: '研判任务中心' })).toBeVisible()
  await expect(page.getByText('case-real-001')).toBeVisible()
  await expect(page.getByText('Agent1 + Agent2')).toBeVisible()
  await expect(page.locator('.task-table-row .status-high')).toBeVisible()
  await expect(page.locator('.task-table-row .status-succeeded')).toBeVisible()
  await expect(page.getByLabel('灾害类型')).toHaveCount(0)
  await expect(page.getByRole('link', { name: '查看case-real-001' }))
    .toHaveAttribute('href', '#/live-jobs/job-real-001')
})

test('真实模式首页展示 SQLite 态势统计', async ({ page }) => {
  test.skip(process.env.VITE_USE_MOCK !== 'false', '仅在真实 API 模式测试中运行')

  await page.route('http://127.0.0.1:8000/api/v1/dashboard', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      json: {
        scope: 'agent1_agent2_local_only',
        four_agent_pipeline_complete: false,
        counts: {
          total: 6,
          active: 2,
          review_required: 1,
          succeeded: 3,
          partial_success: 0,
          failed: 0,
        },
        trend: [
          { time: '04:00', tasks: 0, completed: 0 },
          { time: '08:00', tasks: 2, completed: 1 },
        ],
        recent_jobs: [
          {
            job_id: 'job-recent-001',
            sample_id: 'recent-case-001',
            status: 'running_agent1',
            stage: '正在分析建筑和道路视觉证据',
            progress: 35,
            created_at: '2026-08-08T08:00:00Z',
            scope: 'agent1_agent2_local_only',
            scene_risk_level: null,
            review_required: false,
          },
        ],
      },
    })
  })

  await page.goto('/#/overview')

  await expect(page.getByText('累计真实任务')).toBeVisible()
  await expect(page.getByText('当前范围成功')).toBeVisible()
  await expect(page.getByText('仅表示 Agent1 + Agent2')).toBeVisible()
  await expect(page.getByText('recent-case-001')).toBeVisible()
  await expect(page.getByRole('link', { name: /recent-case-001/ }))
    .toHaveAttribute('href', '#/live-jobs/job-recent-001')
})
