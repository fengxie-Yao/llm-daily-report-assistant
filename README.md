# LLM Daily Report Assistant

基于两份方案文档生成的首版项目，提供一个可运行的 FastAPI 服务，用于处理自然语言任务录入、任务规划、补录完结、日报/周报总结与轻量级 RAG 记忆。

## 当前能力

- 自然语言录入今日任务
- 识别新增、修改、删除、补录完结等操作
- 基于历史记录估算任务耗时
- 自动识别大规模任务并拆分子任务
- 生成格式化的任务规划、日报、周报
- 通过 JSON 持久化实现轻量级知识库
- 预留 OpenAI / LangChain / Chroma 扩展入口

## 项目结构

```text
llm-daily-report-assistant/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── llm_handler.py
│   ├── rag_handler.py
│   ├── models.py
│   ├── storage.py
│   └── utils/
│       ├── format_utils.py
│       └── time_utils.py
├── data/
│   ├── memory.json
│   └── tasks.json
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
└── .env.example
```

## 快速启动

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问：

- `GET /health`
- `POST /task/input`
- `POST /task/summary/daily`
- `POST /task/summary/weekly`
- `POST /task/complete/supplement`

## 示例请求

```json
POST /task/input
{
  "text": "今天的工作：1. 撰写项目方案（紧急，大规模）；2. 回复客户咨询（一般）；3. 整理上周数据（不紧急）；现在时间9:00"
}
```

## 说明

- 当前默认使用规则引擎与本地知识库完成首版能力，无需真实 LLM Key 也可运行。
- 若配置 `OPENAI_API_KEY`，后续可在 `app/llm_handler.py` 中接入真实模型增强解析与摘要能力。
- 若后续需要切换到 Chroma / LangChain，可在 `app/rag_handler.py` 中替换当前 JSON 检索实现。
