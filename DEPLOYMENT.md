# 部署与上线流程

本项目采用和 TEP 项目相同的组合：**GitHub 公共仓库 + GitHub Pages 静态网页 + Render Python Web Service**。GitHub Pages 不运行 Python；浏览器跨域调用 Render 的 FastAPI。仓库、网页与 Render 只含固定参数生成的独立模拟数据。真实生产文件、旧源统计派生副本和本地实验报告只在本机。

## 当前地址

- 仓库：`https://github.com/corookie/industrial-slab-workbench`
- 网页：`https://corookie.github.io/industrial-slab-workbench/`
- 后端：`https://industrial-slab-workbench-api.onrender.com`
- 健康检查：`https://industrial-slab-workbench-api.onrender.com/api/health`

以上地址在首次创建并完成在线检查前只是目标地址。实际状态应以文末上线验收记录为准。

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

在 Render 控制台选择 **New → Blueprint**，连接上面的 GitHub 仓库并采用根目录 `render.yaml`。它定义了一个免费 Python Web Service：

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

Render 免费实例的文件系统在重启、重新部署或休眠后可能清空。服务每次启动会从仓库的独立模拟 CSV 重建数据集；保存的实验历史与图件可能消失，可重新运行生成。免费实例闲置会休眠，首次请求可能较慢。

## 4. 开启 GitHub Pages

仓库 **Settings → Pages → Build and deployment**：选择 **Deploy from a branch**，分支 `main`，目录 `/docs`，保存。等待 Pages 发布后打开网页地址。注意 Pages 只服务 `docs/`，并不会执行后端 Python。

以后修改网页：执行 `python3 scripts/export_pages.py --api-base <实际Render域名>`，审核、提交并推送 `docs/`。修改后端：提交并推送代码，Render 应自动部署；若未触发，在 Render 控制台使用 **Manual Deploy → Deploy latest commit**。

## 5. 上线验收

```bash
curl https://industrial-slab-workbench-api.onrender.com/api/health
.venv/bin/python scripts/verify_public_release.py --url https://industrial-slab-workbench-api.onrender.com
```

健康检查应显示 `mode: public_demo`、`public_data: independent_simulation`。线上 `/api/datasets` 应只有一个独立模拟数据集，10,000 条、G01—G05 五类。网页应能完成筛选、选中记录、运行一次分析、展开三维工况和下载 PNG/PDF/完整实验包。下载图件后检查中文字体与数值；Pages 的 API 请求应指向 Render HTTPS 地址，不能请求本机 `127.0.0.1`。线上上传接口应返回 403。验收结果在实际部署完成后记录。

## 上线验收记录

| 项目 | 状态 |
| --- | --- |
| GitHub 仓库与 Pages | 待线上验证 |
| Render 健康检查 | 待线上验证 |
| 筛选、分析、下载端到端 | 待线上验证 |
| 独立模拟数据与私有隔离 | 本地检查通过；待线上验证 |
