# 部署与上线流程

本项目采用和 TEP 项目相同的组合：**GitHub 公共仓库 + GitHub Pages 静态网页 + Render Python Web Service**。GitHub Pages 不运行 Python；浏览器跨域调用 Render 的 FastAPI。仓库、网页与 Render 只含固定参数生成的独立模拟数据。真实生产文件、旧源统计派生副本和本地实验报告只在本机。

## 当前地址

- 仓库：`https://github.com/corookie/industrial-slab-workbench`
- 网页：`https://corookie.github.io/industrial-slab-workbench/`
- 后端：`https://industrial-slab-workbench-api.onrender.com`
- 健康检查：`https://industrial-slab-workbench-api.onrender.com/api/health`

仓库、Pages 与 Render 服务已创建。实际验收状态见文末记录。

## 1. 本地发布检查

```bash
cd /Users/rowen/Documents/高校/industrial-slab-workbench
./scripts/verify.sh
python3 scripts/export_pages.py --api-base https://industrial-slab-workbench-api.onrender.com
# 首次提交前 git add -A，再运行：
.venv/bin/python scripts/verify_public_release.py
```

`export_pages.py` 将前端构建为 `docs/index.html` 与 `docs/assets/`，网页根路径是 `/industrial-slab-workbench/`，API 地址是 Render 的 HTTPS 域名。它不会删除本机 `docs/` 中的笔记或截图；这些内容被 Git 忽略。`verify_public_release.py` 比较公开 CSV 与固定模拟生成器的字节哈希，并检查 Git 暂存文件和已知源标识。

## 2. 推送 GitHub

在 GitHub 账号 `corookie` 下建立**空的 Public 仓库** `industrial-slab-workbench`，不要勾选自动 README、`.gitignore` 或许可证，以免与本地初始提交冲突。然后在项目目录执行：

```bash
git remote add origin git@github.com:corookie/industrial-slab-workbench.git
git add -A
.venv/bin/python scripts/verify_public_release.py
git commit -m "Publish independent simulation workbench"
git push -u origin main
```

提交前务必确认 `git status --short` 中没有 `runtime/`、`runtime-public/`、`.env`、源数据、旧截图或真实报告。**不要用 `git add -f` 强行提交被忽略的私有内容。**

## 3. 创建 Render 后端

在 Render 控制台选择 **New → Blueprint → Public Git Repository**，填写上面的 GitHub 仓库 URL，分支选 `main`，采用根目录 `render.yaml`，Blueprint 名称为 `industrial-slab-workbench`。当前采用公开仓库 URL，无需授予 GitHub App 额外仓库访问权限。它定义了一个免费 Python Web Service：

| 配置 | 值 |
| --- | --- |
| Python | `.python-version` 固定 3.12 |
| 构建 | `pip install -r backend/requirements.txt` |
| 启动 | `python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT` |
| 健康检查 | `/api/health` |
| `SLAB_MODE` | `public` |
| `SLAB_DATA_DIR` | `/tmp/slab-runtime` |
| `SLAB_ALLOWED_ORIGINS` | `https://corookie.github.io` |

Render 为服务提供 `PORT` 与 `*.onrender.com` HTTPS 域名。确认实际服务 URL；若 Render 分配的域名不同，重新导出 Pages 并推送 `docs/`。此公开演示不需要 API Key，也**不要**配置任何真实数据的存储目录或上传生产文件。`SLAB_ALLOWED_ORIGINS` 只控制浏览器跨域读取，不是用户身份认证，因此服务只提供可公开的模拟数据。

Render 免费实例的文件系统在重启、重新部署或休眠后可能清空。服务每次启动会从仓库的独立模拟 CSV 重建数据集；保存的实验历史与图件可能消失，可重新运行生成。免费实例闲置会休眠，首次请求可能较慢。网页默认使用内置的 1,000 条独立模拟记录，统计、筛选、分页、记录与板坯三维示意、CSV 导出无需等待后端。后台连接成功后，下拉框增加 10,000 条完整示例，**不会自动切换**。用户手动选择后，图表、记录和样本数统一使用所选数据集；两个范围不会混合。连接失败时，快速示例继续可用，可点“重新连接”。Python 实验和报告需要选择已连接的完整数据集。

`npm run dev` 和 `npm run build` 会先执行 `scripts/build_quick_demo.py`。该脚本只从已校验的公开独立模拟 CSV 中，每类等距选取 200 条，生成 `frontend/src/data/quick-demo.json`。前端在浏览器中计算这个小数据集的筛选统计；完整实验的 Python 计算方法未改变。发布审计检查内置数据与独立模拟来源一致，不能替换为真实生产数据。

## 4. 开启 GitHub Pages

仓库 **Settings → Pages → Build and deployment**：选择 **Deploy from a branch**，分支 `main`，目录 `/docs`，保存。等待 Pages 发布后打开网页地址。注意 Pages 只服务 `docs/`，并不会执行后端 Python。

以后修改网页：执行 `python3 scripts/export_pages.py --api-base https://industrial-slab-workbench-api.onrender.com`，审核、提交并推送 `docs/`，Pages 会自动更新。当前 Render 使用公开仓库 URL，推送代码后需要在服务页执行 **Manual Deploy → Deploy latest commit**；改动 `render.yaml` 后可在 Blueprint 页执行 **Manual sync**。若以后连接 GitHub App，才可以进一步配置自动部署。

## 5. 上线验收

```bash
curl https://industrial-slab-workbench-api.onrender.com/api/health
.venv/bin/python scripts/verify_public_release.py --url https://industrial-slab-workbench-api.onrender.com
.venv/bin/python scripts/verify_online.py
```

健康检查应显示 `mode: public_demo`、`public_data: independent_simulation`。线上 `/api/datasets` 应只有一个独立模拟数据集，10,000 条、G01—G05 五类。网页应能完成筛选、选中记录、运行一次分析、展开三维工况和下载 PNG/PDF/完整实验包。下载图件后检查中文字体与数值；Pages 的 API 请求应指向 Render HTTPS 地址，不能请求本机 `127.0.0.1`。线上上传接口应返回 403。`verify_online.py` 会实际运行一份分析、下载文件并检查重跑一致性，结果保存在被 Git 忽略的 `runtime/online-verification/`。

## 上线验收记录

| 项目 | 状态 |
| --- | --- |
| GitHub 仓库与 Pages | 2026-10-03 已上线，HTTPS 页面正常 |
| Render 健康检查 | 已通过，公开独立模拟模式；中文字体已部署 |
| 筛选、分析、下载端到端 | 已通过；G01 筛选 2,000 条，控制工况后分组 175 条；分组、快照、下载 CSV 一致；按参数重跑结果一致 |
| 图件与报告 | PNG 中文正常；PDF、关系 CSV、统计 CSV、HTML 报告、实验 ZIP 下载正常；ZIP 完整性检查通过 |
| 独立模拟数据与私有隔离 | 本地与线上检查通过，唯一公开数据集 10,000 条，上传请求返回 403 |

## 两条发布路径与更新顺序

```mermaid
flowchart LR
  A[本地源码与发布检查] --> B[GitHub main]
  B --> C[docs 静态构建]
  C --> D[GitHub Pages 网页]
  B --> E[Render 手动部署]
  E --> F[FastAPI 分析服务]
  D -->|HTTPS 请求| F
  F --> G[统计结果与图件报告]
```

后端接口有兼容性改动时，先上线后端并确认健康检查，再发布调用新接口的网页。部署失败时可在 Render 查看构建和运行日志；Pages 状态在 GitHub Actions 的 `pages build and deployment` 查看。网页可通过恢复上一版 `docs/` 并推送回滚；后端可在 Render 的旧部署记录选择回滚，或使用 **Deploy a specific commit** 部署已验证版本。新代码先运行本地检查，再上线；每次发布后重新验收筛选、分析与下载。

参考：[GitHub Pages 发布来源](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)、[Render Web Service](https://render.com/docs/web-services)、[Render 免费实例限制](https://render.com/docs/free)。
