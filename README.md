# SLAB LAB · 工业板坯数据分析工作台

Vue 3、ECharts、Three.js 与 Python 组成的可运行个人工程项目。网页包括热轧工艺示意、筛选统计和记录联动、三维工况探索，以及“变量变化多少，粗轧温降平均变化多少”的分析实验。Python 完成清洗、分组统计、线性关联估计与 Matplotlib 科研图组；报告、图件、统计表和实验包可下载。

> **公开网站只使用完全独立设定参数的模拟数据。** G01—G05 是虚构类别，每类 2,000 条，共 10,000 条；不代表宝钢钢种、产量、工况分布或真实分析结论。真实生产数据和从其统计结构派生的旧演示副本只保留在本机私有目录，不进入公开仓库或 Render。

## 在线与本地运行

- 网页：[打开 SLAB LAB](https://corookie.github.io/industrial-slab-workbench/)，GitHub Pages 发布 `main/docs`。
- Python 接口：[Render 健康检查](https://industrial-slab-workbench-api.onrender.com/api/health)。
- 源码：[GitHub 仓库](https://github.com/corookie/industrial-slab-workbench)。
- 部署步骤：[DEPLOYMENT.md](DEPLOYMENT.md)。

本机直接运行：

```bash
./scripts/start.sh --public --open
```

首次运行会建立 Python 环境、安装依赖并构建网页。`--public` 只加载独立模拟数据，禁止上传文件。本机分析自己的 Excel/CSV 时，用 `./scripts/start.sh --private --open`；需要确认字段、单位和缺失值后才能导入。根目录的 `.env` 是本机配置，Git 忽略它。Python 3.12 与 Node 22 为推荐版本。

## 演示流程

1. 首页查看加热、除鳞、粗轧、精轧的**工艺示意**。设备数量、时间和动画节拍不代表真实产线。
2. 进入数据工作台，在页面顶部选 G01 及厚度、出炉温度、粗轧过程时间范围；图表、表格和样本数同步更新。点击散点或表格查看同一记录，可按需展开板坯三维示意。
3. 进入分析实验，选择一个变量（例如粗轧厚度或过程时间）、分组边界和相近工况，运行分析。先看分组统计与工况检查，再看“结论”卡片的数值关系。
4. 可展开 Three.js 三维工况：出炉温度、粗轧过程时间、粗轧厚度三轴，颜色表示温降。下载 Matplotlib 图件、全部变量关系报告、统计 CSV 或完整实验包。

演示数据字段：[data/examples/FIELDS.md](data/examples/FIELDS.md)。

## 架构与实现

| 部分 | 实现 |
| --- | --- |
| 网页 | Vue 3；ECharts 聚合、分布与散点；Three.js 板坯与三维工况；分页记录与筛选联动 |
| 服务 | FastAPI；Pandas / NumPy 数据整理；SciPy 与线性回归统计；Matplotlib 制图 |
| 数据隔离 | 公开服务只认独立模拟 release；私有数据使用另一个本机目录；公开模式拒绝上传和访问私有记录 |
| 复现 | 保存筛选范围、参数、样本快照指纹和结果；可按保存参数再次运行 |
| 部署 | `main/docs` 静态页面 + Render Python Web Service，与 TEP 项目同类架构 |

多文件、多工作表可预览并映射字段。板坯编号关联使用唯一性和 `many_to_one` 检查，避免重复关联造成样本膨胀。网页数值分布统计基于完整筛选范围，散点最多绘制 2,500 个点，记录每页 30 条。实验分组采用左闭右开、末组含右端点，报告记录实际分析样本量、均值、样本标准差、控制工况与组间差异。

量化结论是**当前筛选范围下的线性关联估计**，不是因果效应或生产控制建议。HC3 95% 区间是已计算的异方差稳健区间，未校正生产记录的时间相关性；样本内 R² 也不是测试集性能。独立模拟数据的数值关系只用于演示软件流程。

## 验证与限制

```bash
./scripts/verify.sh
.venv/bin/python scripts/verify_public_release.py
```

后端测试覆盖样本计数、关联、分析边界、复现、公开模式隔离与量化估计。前端生产构建和浏览器交互验证在 `frontend/` 运行。Render 免费实例闲置后可能休眠，运行文件是临时存储，重启后历史实验会消失；重新运行可重新生成报告。公开服务不接收生产数据，真实数据只在本机私有模式处理。网页首次连接时显示等待状态；临时网络故障或启动中的 502/503/504 会自动重试，失败后可点击“重新加载数据”。

本项目没有 AI 对话或通用智能体功能。三维热轧过程属于示意动画，没有空间测温数据时不会显示真实温度场。

科研图件随项目附带 Noto Sans CJK SC 字体，来源为 [Noto CJK 官方仓库](https://github.com/notofonts/noto-cjk)，按 SIL Open Font License 使用；许可证见 `backend/assets/fonts/LICENSE.txt`。因此 Render 无需另装系统中文字体。
