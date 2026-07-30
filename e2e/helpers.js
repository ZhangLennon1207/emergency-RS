export async function resetDemoData(page, route = '/#/overview') {
  await page.goto(route)
  await page.evaluate(() => window.localStorage.clear())
  await page.reload()
}

export const completedTaskId = 'TASK-20260729-001'
