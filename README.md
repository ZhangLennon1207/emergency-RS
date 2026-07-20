# Emergency RS Agent Platform（应急遥感智能体平台）

面向遥感灾害评估的生产级应急管理指挥面板。  
UI 专为向应急管理部门演示而设计，展示一个具备不确定性感知能力的遥感智能体系统如何以商业化指挥平台形态呈现。

## 功能特性

- 指挥中心风格的灾害监测仪表盘
- 带置信度标注的区域级研判结果表
- 图像-掩码-文本对齐的证据链工作流
- AI 智能体报告中心，输出结构化灾情简报
- 静态构建产物，支持 GitHub Pages、Vercel 或 Netlify 部署

## 技术栈

- React 19
- Vite 8
- Recharts
- Lucide React

---

## 团队协作指南

### 环境准备（每个成员只需做一次）

1. 安装 [GitHub Desktop](https://desktop.github.com/)（推荐）或 Git
2. 克隆仓库：GitHub Desktop → File → Clone repository → 输入 `ZhangLennon1207/emergency-RS`
3. 在 GitHub Desktop 中设置用户信息：File → Options → Git → 填写 Name 和 Email

### 日常开发流程

> **核心原则：永远不要在 `main` 分支上直接修改代码！**

```text
① 开工前同步  →  点 Fetch origin → Pull，拉取最新代码
② 创建分支    →  顶部点分支名 → New branch，命名如 feature/你的功能名
③ 写代码      →  在 IDE 里正常开发
④ 提交        →  左侧勾选改动的文件 → 写摘要 → 点 Commit to 分支名
⑤ 推送        →  点 Publish branch（首次）/ Push origin
⑥ 创建 PR     →  点 Create Pull Request，自动跳转 GitHub 网页
⑦ 代码审查    →  其他成员 Review 通过后点 Merge
⑧ 同步        →  切回 main 分支，点 Fetch origin → Pull
```

### 分支命名规范

| 前缀 | 用途 | 示例 |
| ---- | ---- | ---- |
| `feature/` | 新功能 | `feature/damage-assessment` |
| `fix/` | 修复 Bug | `fix/chart-overflow` |
| `docs/` | 文档更新 | `docs/api-guide` |
| `refactor/` | 代码重构 | `refactor/data-fetching` |

### 提交信息规范

```text
feat: 添加了xxx功能
fix: 修复了xxx问题
docs: 更新了xxx文档
refactor: 重构了xxx模块
```

### 冲突解决

1. 如果 Push 或创建 PR 时提示冲突，GitHub Desktop 会标出冲突文件
2. 打开冲突文件，手动选择保留哪部分代码，删除 `<<<<<<<` `=======` `>>>>>>>` 标记
3. 返回 GitHub Desktop，点 Commit merge 完成合并
4. 继续 Push 即可

---

## 项目结构

```text
emergency-RS/
├── src/          # 前端源码
├── backend/      # 后端（大模型相关代码统一放这里，逐步用 AI 整理）
├── doc/          # 方案文档
├── public/       # 静态资源
└── CHANGELOG.md  # 更新日志（每次修改后建议更新）
```

---

## 本地开发

```bash
npm install
npm run dev
```

## 生产构建

```bash
npm run build
npm run preview
```

## GitHub Pages 部署

本仓库包含 `.github/workflows/deploy.yml`，用于 GitHub Pages 自动部署。

1. 将仓库推送至 GitHub 的 `main` 分支
2. 在 GitHub 仓库设置中，启用 Pages，选择 `GitHub Actions` 作为部署来源
3. 每次推送至 `main` 分支，站点将自动构建并发布

### 手动部署至 `gh-pages`

```bash
npm run deploy
```
