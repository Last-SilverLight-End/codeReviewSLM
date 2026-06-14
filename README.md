# Local AI Code Review Platform

로컬 환경에서 동작하는 AI 기반 코드 리뷰 및 개발 보조 플랫폼입니다.  
소스 파일 또는 zip 프로젝트를 업로드하면 코드를 파싱, 청킹, 임베딩한 뒤 로컬 LLM을 통해 코드 리뷰와 프로젝트 기반 질의응답을 제공합니다.

외부 클라우드 LLM API에 의존하지 않고 Ollama 기반 로컬 모델을 사용합니다. 코드와 대화 데이터는 로컬 인프라 안에서 처리되며, FastAPI, Next.js, Celery, Redis, PostgreSQL/pgvector, Elasticsearch, Kibana를 조합해 동작합니다.

---

## 목차

- [1. 개요](#1-개요)
- [2. 설명](#2-설명)
- [3. 사용 방법](#3-사용-방법)

---

## 1. 개요

Local AI Code Review Platform은 로컬 개발 환경에서 코드 리뷰, 코드 검색, 프로젝트 질의응답, 이미지 기반 문제 분석을 지원하는 AI 시스템입니다.

사용자는 단일 소스 파일 또는 zip 프로젝트를 업로드할 수 있습니다. 시스템은 업로드된 코드를 Tree-sitter로 파싱하고, 함수/클래스/모듈 단위로 청킹한 뒤 Ollama 임베딩 모델로 벡터화합니다.

저장된 코드 청크는 PostgreSQL/pgvector와 Elasticsearch를 함께 사용해 검색합니다. pgvector는 의미 기반 검색을 담당하고, Elasticsearch는 함수명, 파일명, 에러 문자열 같은 키워드 기반 전문검색과 운영 로그 확인을 담당합니다.

---

## 2. 설명

### 주요 기능

- 로컬 LLM 기반 코드 리뷰
- 단일 소스 파일 업로드 및 리뷰
- zip 프로젝트 업로드 및 코드 청킹
- PostgreSQL/pgvector 기반 의미 검색
- Elasticsearch 기반 BM25 코드 검색 및 운영 로그 저장
- 프로젝트 기반 RAG Q&A
- SSE 스트리밍 응답
- 이미지 분석과 코드 컨텍스트를 결합한 멀티모달 분석
- Kibana를 통한 로그 및 검색 인덱스 확인

### 기술 스택

| 영역 | 기술 |
| --- | --- |
| Frontend | Next.js, React, Tailwind CSS |
| Backend | FastAPI, SQLAlchemy asyncio, Pydantic |
| Async Worker | Celery |
| Broker / Cache / Session | Redis |
| Database | PostgreSQL, pgvector |
| Local LLM | Ollama, qwen3 |
| Embedding | Ollama, nomic-embed-text |
| Vision Model | Ollama, llava |
| Code Parsing | Tree-sitter |
| Log / Search | Elasticsearch, Kibana |
| Infra | Docker Compose |

### 구조 요약

```text
[Next.js UI] (localhost:3000)
    |
    | HTTP / SSE
    v
[FastAPI Backend] (localhost:8000)
    |
    |-- Celery Worker
    |-- Redis
    |-- PostgreSQL + pgvector
    |-- Elasticsearch + Kibana
    `-- Ollama (Windows native process)
          |-- qwen3
          |-- nomic-embed-text
          `-- llava
```

상세한 프로젝트 설명, 아키텍처, 데이터 흐름, 시나리오는 [docs/overview.md](docs/overview.md)를 참고하세요.

---

## 3. 사용 방법

자세한 설치 및 실행 절차는 [docs/setup.md](docs/setup.md)를 참고하세요.

### 설치

```powershell
git clone https://github.com/Last-SilverLight-End/codeReviewSLM.git
cd codeReviewSLM
Copy-Item .env.example .env
```

`.env`를 로컬 환경에 맞게 수정한 뒤 필요한 Ollama 모델을 내려받습니다.

```powershell
ollama pull qwen3:8b
ollama pull nomic-embed-text
ollama pull llava:7b
```

백엔드와 프론트엔드 의존성을 설치합니다.

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
cd ..
```

```powershell
cd frontend
npm install
cd ..
```

Docker 인프라를 실행하고 DB 마이그레이션을 적용합니다.

```powershell
docker compose up -d

cd backend
.\venv\Scripts\activate
alembic upgrade head
cd ..
```

### 실행

```bat
start.bat
```

실행 후 주요 접속 주소는 다음과 같습니다.

| 화면 | URL |
| --- | --- |
| App UI | `http://localhost:3000` |
| FastAPI | `http://localhost:8000` |
| Swagger | `http://localhost:8000/docs` |
| Elasticsearch | `http://localhost:9200` |
| Kibana | `http://localhost:5601` |

### 상태 확인

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-components.ps1
```

### 종료

```bat
stop.bat --all --no-pause
```

### 추가 문서

| 문서 | 설명 |
| --- | --- |
| [docs/overview.md](docs/overview.md) | 프로젝트 설명, 아키텍처, 주요 기능, 시나리오 |
| [docs/setup.md](docs/setup.md) | 로컬 설치, 환경 변수, 모델 준비, 실행/종료, Kibana 확인 |
| [docs/verification.md](docs/verification.md) | 검증 현황, RAG Q&A 검증 예시, 40초 검증 기준 |
