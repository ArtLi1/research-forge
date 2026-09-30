# ResearchForge

面向科研构思的单用户 AI 工作台，将论文阅读、知识整理与研究方案探索连接起来。

ResearchForge 从论文中提取**研究场景**与**算法机制**，通过 Inspiration-RAG（围绕研究启发的检索增强生成）为研究目标寻找可迁移的思路，再生成、校验和修订候选方案。用户可以查看过程与反馈，决定哪些想法和方案值得保留。

## 核心功能

- **文献管理**：批量上传 PDF、内容去重、全局文献库与项目关联。
- **知识提取**：解析论文、按章节分块，提取研究场景与算法机制知识卡，保留知识版本。
- **检索与比较**：按全局、项目或指定论文检索正文与启发知识，支持 2–5 篇论文的五维比较。
- **研究构思**：围绕目标检索场景与算法启发，生成三个候选方案，执行约束校验、风险评估与反馈修正。
- **人工评审**：记录个人想法、评估可行性、修订或接受方案，并查看版本历史和 Agent 执行过程。
- **项目记忆**：将已采纳想法与已确认方案沉淀为项目知识。
- **任务追踪**：后台处理耗时任务，通过 SSE 实时展示进度。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Element Plus、Pinia |
| API | FastAPI、Pydantic、SQLAlchemy、Alembic |
| Agent | LangGraph、OpenAI 兼容的 Chat Completions 服务 |
| 文献处理与检索 | PyMuPDF4LLM、Chroma |
| 数据与任务 | PostgreSQL、Redis、RQ |
| 开发检查 | pytest、Ruff、mypy、Vitest、ESLint |

```text
Vue 工作台
    │ REST / SSE
    ▼
FastAPI ─────────── PostgreSQL（项目、论文、方案）
    │
    ▼
Redis / RQ Worker
    ├── PDF 解析与知识提取
    ├── Chroma 向量检索
    └── LangGraph 研究构思 ── LLM 服务
```

## 快速开始

以下命令以 **Windows + PowerShell + Conda** 为例，在仓库根目录执行。

### 1. 准备环境

- Python **3.12**；下面使用名为 `drl` 的 Conda 环境。
- Node.js **22** 与 npm。
- 已启动的 PostgreSQL 和 Redis，以及一个已创建、可连接的 PostgreSQL 数据库。
- OpenAI 兼容的 Chat Completions 服务，用于知识提取与 Agent 功能。

PostgreSQL 和 Redis 可以部署在本机或远程服务器。Chroma 由项目启动脚本运行。

### 2. 安装依赖

如果尚未创建 Python 环境：

```powershell
conda create -n drl python=3.12 -y
```

安装后端与前端依赖：

```powershell
conda run -n drl python -m pip install "./backend[dev]"
npm --prefix frontend ci
```

### 3. 配置服务

首次使用时复制配置模板：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，将示例地址和路径替换为自己的配置：

| 配置 | 说明 |
| --- | --- |
| `POSTGRES_HOST`、`POSTGRES_PORT`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB` | PostgreSQL 连接信息 |
| `REDIS_HOST`、`REDIS_PORT`、`REDIS_DB` | Redis 连接信息 |
| `CHROMA_HOST`、`CHROMA_PORT`、`CHROMA_DATA_DIR` | Chroma 监听地址与本地数据目录 |
| `PAPER_STORAGE_DIR` | 上传论文的存储目录；相对路径以服务工作目录为基准 |
| `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` | 模型服务地址、密钥与默认模型 |
| `LLM_EXTRACTION_MODEL` | 知识提取模型，填写服务支持的模型名称 |

完整选项见 [.env.example](.env.example)。真实配置 `.env` 已加入 Git 忽略规则。

### 4. 启动应用

```powershell
.\start_all.cmd
```

脚本使用 `drl` 环境，先执行数据库迁移，再分别启动 Chroma、两个 RQ Worker、API 和前端。运行期间保持这些终端开启。

| 入口 | 地址 |
| --- | --- |
| 工作台 | http://localhost:5173 |
| API 文档 | http://127.0.0.1:8000/docs |
| 健康检查 | http://127.0.0.1:8000/api/v1/health |

<details>
<summary>手动启动各服务</summary>

先在仓库根目录执行数据库迁移：

```powershell
Set-Location backend
conda run -n drl alembic upgrade head
```

然后打开 **四个终端**，分别进入 `backend` 目录，每个终端执行以下一条命令：

```powershell
conda run --no-capture-output -n drl python -m app.scripts.run_chroma
conda run --no-capture-output -n drl python -m app.scripts.run_worker paper_parse project_update scheme_generate default
conda run --no-capture-output -n drl python -m app.scripts.run_worker knowledge_extract
conda run --no-capture-output -n drl uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

另开一个终端，进入 `frontend` 目录启动前端：

```powershell
npm run dev
```

</details>

## 使用流程

1. **创建项目**：确定研究主题，在全局文献库上传文本型 PDF，并关联到项目。
2. **整理文献**：等待解析和知识提取完成，查看知识卡，补充自定义元数据或比较多篇论文。
3. **探索思路**：在“个人想法”中记录并评估思路，或直接在“研究构思工作台”填写研究目标。
4. **评审方案**：查看候选方案、Agent 过程、约束检查与风险反馈，提出修改意见并保留版本历史。
5. **沉淀结果**：明确接受合适的方案，将其与已采纳想法一起保存到项目知识。

生成研究方案前，项目需关联至少一篇已完成知识提取的论文。存在硬约束违规的方案版本不能直接接受。

当目标涉及计算卸载时，检索规划、方案生成、修订、想法评估和约束检查会附加计算卸载研究规则，
关注任务依赖、通信与排队开销、资源容量、可观测信息以及时延与能耗的取舍。
输入中缺少的条件列为假设或待确认问题，不作为论文事实；其他研究领域仍使用通用工作流。
生成和修订版本记录基础提示词与附加规则的版本名称。

## 目录结构

```text
.
├── backend/
│   ├── app/
│   │   ├── agents/        # Agent 状态与工具
│   │   ├── api/           # API 路由
│   │   ├── models/        # 数据模型
│   │   ├── prompts/       # 提示词模板
│   │   ├── providers/     # 模型、存储与向量服务
│   │   ├── services/      # 业务逻辑与工作流
│   │   └── tasks/         # 后台任务
│   ├── alembic/           # 数据库迁移
│   ├── scripts/           # 集成验收脚本
│   └── tests/
├── frontend/
│   ├── src/               # 页面、组件、状态与 API 客户端
│   └── tests/
├── .env.example           # 环境配置模板
└── start_all.cmd          # Windows 开发启动脚本
```

## 开发与验证

本地代码导航维护在根目录 `CODE_INDEX.md`（由 `.gitignore` 排除，首次建立后按修改增量更新）。
先查询索引，再沿相关调用链读取代码；修改后同步职责和调用关系，以实际代码为准。

后台队列提交统一由 `TaskService` 处理，同步 Redis/RQ 操作在线程中执行。
任务事件支持进度、完成、失败、取消和保活；前端切换任务或离开页面时关闭旧连接。
向量重建在新内容写入成功后清理同篇论文的旧向量，避免模型调用或写入失败时提前清空旧索引。
数据库与 Chroma 的写入并非跨服务原子事务，失败后仍需通过任务重试完成一致性恢复。

在仓库根目录执行后端检查：

```powershell
Set-Location backend
conda run -n drl pytest -q
conda run -n drl ruff check .
conda run -n drl mypy app
```

进入前端目录执行测试、静态检查与构建：

```powershell
Set-Location ..\frontend
npm test
npm run lint
npm run build
```

应用及依赖服务全部启动后，可在 `backend` 目录运行基础流程验收：

```powershell
conda run -n drl python scripts\smoke_m0_m2.py
```
