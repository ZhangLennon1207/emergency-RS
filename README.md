# Emergency RS Agent Platform（应急遥感智能体平台）

仓库建好了喵
协作者加入之后
大家把做好的东西可以整理到这里面
后端那些大模型啥的可以先一概扔到backend里面，慢慢让AI整理
方案啥的放在doc里了
然后修改完之后最好让AI写一下CHANGELOG


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

1. 将仓库推送至 GitHub 的 `main` 分支。
2. 在 GitHub 仓库设置中，启用 Pages，选择 `GitHub Actions` 作为部署来源。
3. 每次推送至 `main` 分支，站点将自动构建并发布。

## 手动部署至 `gh-pages`

```bash
npm run deploy
```

## 建议仓库名

`emergency-rs-agent-platform`
