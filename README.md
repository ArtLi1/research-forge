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
| `PAPER_STORAGE_DIR` | 上传论文的存储目录；相对路径固定以 `backend` 为基准 |
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
conda run --no-capture-output -n drl python -m app.scripts.run_worker paper_parse scheme_generate
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
│   │   ├── agents/        # 类型化状态、上下文快照、独立工作流与运行协调
│   │   ├── api/           # API 路由
│   │   ├── models/        # 数据模型
│   │   ├── prompts/       # 提示词模板
│   │   ├── providers/     # 模型、存储与向量服务
│   │   ├── rag/           # 检索范围、知识预算、结果解码与去重
│   │   ├── services/      # 产品用例、版本检查与人工确认事务
│   │   └── tasks/         # 统一运行器、租约、心跳、恢复与派发
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

内部设计、工作流和事务边界见 [ARCHITECTURE.md](ARCHITECTURE.md)。

后台队列提交统一由 `TaskService` 处理，同步 Redis/RQ 操作在线程中执行。
数据库任务是持久化待派发记录；Redis 暂不可用时保留排队状态，API 内的调度器会继续派发。
运行器领取带令牌的租约并续租，过期任务会恢复，旧工作进程不能提交结果。
LangGraph 每完成一个阶段便保存 `AgentRun.checkpoint`，进程中断后从最近阶段继续。
所有候选方案及任务成功状态在同一事务提交；模型服务调用仍为至少一次语义。
任务事件支持进度、完成、失败、取消和保活；前端切换任务或离开页面时关闭旧连接。
正文只检索数据库已激活的块，知识按当前版本检索；已提交知识历史保留以支持正在执行的研究快照。
向量重建分批写入，成功后只清理开始前观察到的旧正文或未提交知识，避免删除后续任务索引。
数据库与 Chroma 的写入并非跨服务原子事务，失败后仍需通过任务重试完成一致性恢复。

在仓库根目录执行后端检查：

```powershell
Set-Location backend
conda run -n drl pytest -q
conda run -n drl ruff check .
conda run -n drl mypy app
conda run -n drl ruff format --check app tests alembic
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

默认测试使用临时 SQLite，模型、队列和向量服务由可控适配器替代；真实 PDF、HTTP 接口、
数据库事务、工作流恢复及人工确认均参与测试。设置 `TEST_DATABASE_URL` 为专用 PostgreSQL
测试库时，每个测试建立独立临时 schema，并验证真实并发领取。CI 同时执行 PostgreSQL
迁移、一致性检查、后端测试以及前端检查。测试不会访问所配置的真实 LLM。

## 升级已有部署

先停止旧 API 和所有 Worker，备份 PostgreSQL 与论文/Chroma 数据，然后在 `backend` 中执行
`alembic upgrade head`，再使用原启动入口启动新版。迁移 `0004` 增加任务租约与 Agent 检查点；
旧未完成任务重新排队，同篇论文只保留较新的处理任务，已有论文、知识、方案与历史版本保留。
旧运行不具有可恢复检查点，将作为中断记录保留。不要同时运行升级前后的 Worker。

生产部署使用常驻进程管理器启动 API/Worker，不使用开发模式的 `--reload`。
增加并行任务容量可启动更多 Worker；API 调度器使用数据库行锁协调多个实例。
保持 `TASK_LEASE_SECONDS` 至少为心跳间隔的三倍，设置模型超时、输出预算、检索并发与修正次数。
业务日志为带请求/任务 ID 的 JSON，公开接口只返回可供用户处理的错误。
本产品保持单用户定位，部署在受信网络或带认证的反向代理之后。
