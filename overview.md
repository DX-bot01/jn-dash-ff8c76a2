# 济南区域 · 销售数据监督仪表盘

## v5.3 全自动固定网址部署 (2026-06-16)

### 核心变化
不再需要手动拖拽 Netlify Drop！通过 Netlify API 实现全自动部署到固定网址。

```
你说「阿龙，更新发布」→ 自动刷新数据 → 自动打包 → 自动部署到固定网址
```

### 文件结构

```
jinan-dashboard/
├── index.html              ← 仪表盘前端
├── convert.py              ← 数据转换器 v5.0
├── deploy.py               ← 部署脚本 v5.3 (支持 API 自动部署)
├── deploy.bat              ← 一键部署（本地查看+分享）
├── netlify_setup.py        ← Netlify 一次性设置（创建站点）
├── netlify_setup.bat       ← 同上
├── start-server.bat        ← 一键启动本地预览
├── .netlify-config.json    ← Netlify 配置（token+site_id，不提交）
├── .gitignore              ← 保护敏感文件
├── data/                   ← JSON输出
│   ├── daily.json
│   ├── weekly.json
│   ├── monthly.json
│   ├── targets.json
│   └── history/
└── release/                ← 部署包（临时）
```

### 使用流程

#### 一次性设置（仅首次）

1. 双击 `netlify_setup.bat`
2. 打开 https://app.netlify.com/user/applications/personal 创建 token
3. 粘贴 token → 自动创建站点 → 获得固定网址

#### 每日更新+发布

- **方式1**：跟我说「阿龙，更新发布济南仪表盘」→ 全自动
- **方式2**：双击 `deploy.bat` → 自动完成

### 本地查看

1. 从总部系统导出 CSV（客单分析报表、类别销售分析、充值销售汇总）
2. 覆盖到 `D:\zkn\济南\数据\`，命名按上述规范
3. 双击 `start-server.bat`
4. 浏览器自动打开 `http://localhost:8765`

### v5.0 数据架构

```
D:\zkn\济南\数据\
├── 本月_客单分析报表.csv   ← 当月每日明细（带时间列）
├── 本月_类别销售分析.csv   ← 当月品类（带日期列）
├── 本月_充值销售汇总.csv   ← 当月储值（带日期列）
├── 上月_客单分析报表.csv   ← 上月（可选，用于月环比）
├── 上月_类别销售分析.csv   ← 上月（可选）
└── 上月_充值销售汇总.csv   ← 上月（可选）
```
