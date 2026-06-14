# Local AI Code Review Platform

로컬 환경에서 동작하는 AI 기반 코드 리뷰 및 개발 보조 플랫폼입니다.  
소스 파일 또는 zip 프로젝트를 업로드하면 코드를 파싱, 청킹, 임베딩한 뒤 PostgreSQL/pgvector에 저장하고, 로컬 LLM을 통해 코드 리뷰와 프로젝트 기반 질의응답을 제공합니다.

외부 클라우드 LLM API에 의존하지 않고 Ollama 기반 로컬 모델을 사용합니다. 코드와 대화 데이터는 로컬 인프라 안에서 처리되며, FastAPI, Next.js, Celery, Redis, PostgreSQL/pgvector, Elasticsearch, Kibana를 조합해 실제 개발 도구에 가까운 AI 파이프라인을 구성합니다.

---

## 목차

- [1. 개요](#1-개요)
- [2. 목적](#2-목적)
- [3. 아키텍처](#3-아키텍처)
- [4. 시스템 구조](#4-시스템-구조)
- [5. 내역](#5-내역)
- [6. 시나리오](#6-시나리오)
- [7. 결과](#7-결과)
- [8. 검증 현황](#8-검증-현황)
- [9. 실행 방법](#9-실행-방법)
- [10. 얻은 점](#10-얻은-점)

---

## 1. 개요

Local AI Code Review Platform은 로컬 개발 환경에서 코드 리뷰, 코드 검색, 프로젝트 질의응답, 이미지 기반 문제 분석을 지원하는 AI 시스템입니다.

사용자가 단일 소스 파일을 업로드하면 시스템은 해당 파일을 파싱하고 로컬 LLM으로 리뷰를 생성합니다. zip 프로젝트를 업로드하면 여러 소스 파일을 함수, 클래스, 모듈 단위로 청킹하고, 각 청크를 임베딩해 벡터 검색 가능한 지식 베이스로 저장합니다.

이후 사용자는 자연어로 프로젝트에 대해 질문할 수 있습니다. 시스템은 질문과 관련된 코드 청크를 PostgreSQL/pgvector의 의미 검색과 Elasticsearch의 BM25 전문검색으로 함께 찾고, 합쳐진 코드 컨텍스트를 LLM에 전달해 실제 코드에 근거한 답변을 생성합니다.

---

## 2. 목적

이 프로젝트의 목적은 개발 과정에서 반복적으로 발생하는 코드 이해, 리뷰, 디버깅, 변경 영향 분석을 로컬 AI 시스템으로 지원하는 것입니다.

주요 목표는 다음과 같습니다.

- 프로젝트 코드를 업로드하고 검색 가능한 코드 지식 베이스로 변환합니다.
- 로컬 LLM을 사용해 코드 리뷰와 개발 질문에 대한 답변을 생성합니다.
- RAG 구조를 통해 답변이 실제 프로젝트 코드에 근거하도록 만듭니다.
- 이미지, 로그, 웹 검색 결과를 함께 활용해 문제 분석 범위를 넓힙니다.
- 비동기 작업, 스트리밍 응답, 로그 관측성을 포함한 운영 가능한 AI 개발 도구 구조를 실험합니다.

---

## 3. 아키텍처

```text
[Next.js UI] (localhost:3000)
    |
    | HTTP / SSE
    v
[FastAPI Backend] (localhost:8000)
    |
    |-- Auth API
    |     `-- JWT Access / Refresh Token
    |
    |-- Code API
    |     |-- file upload
    |     |-- project zip upload
    |     |-- Tree-sitter parsing
    |     `-- chunk metadata
    |
    |-- Chat / Review API
    |     |-- project RAG Q&A
    |     |-- streaming response
    |     |-- image + code context analysis
    |     `-- web search augmented response
    |
    |-- Celery Worker
    |     `-- asynchronous code review task
    |
    |-- Redis
    |     |-- Celery broker
    |     |-- refresh token store
    |     `-- cache layer
    |
    |-- PostgreSQL + pgvector
    |     |-- users / projects / reviews
    |     |-- conversations / messages
    |     `-- code files / code chunks / embeddings
    |
    |-- Elasticsearch
    |     |-- logs and operational search pipeline
    |     |-- BM25 code search index
    |     `-- Kibana dashboard / Discover
    |
    `-- Ollama (native Windows process)
          |-- qwen3: code review, chat, RAG answer
          |-- nomic-embed-text: code embedding
          `-- llava: image analysis
```

Ollama는 Docker 컨테이너가 아니라 Windows 네이티브 프로세스로 실행됩니다. PostgreSQL, Redis, Elasticsearch, Kibana는 Docker Compose로 실행합니다.

---

## 4. 시스템 구조

### Frontend

Next.js UI는 사용자가 실제로 접하는 화면을 담당합니다.

로그인, 회원가입, 파일 업로드, 프로젝트 업로드, 채팅, 리뷰 결과 표시, RAG 참조 표시, 웹 검색 출처 표시, 관리자 로그 화면이 이 계층에 포함됩니다. LLM 응답은 길어질 수 있기 때문에 일반 JSON 응답뿐 아니라 SSE 스트리밍 응답도 처리합니다.

### Backend

FastAPI는 모든 애플리케이션 요청의 중심입니다.

인증 요청을 처리하고, 업로드된 파일을 파싱 서비스로 넘기며, 임베딩과 벡터 저장을 호출합니다. 대화형 요청에서는 현재 대화 히스토리, 프로젝트 컨텍스트, 이미지 분석 결과, 웹 검색 결과를 조합해 Ollama 호출에 필요한 메시지를 구성합니다.

### Async Worker

Celery는 오래 걸리는 코드 리뷰 작업을 백그라운드에서 처리합니다.

LLM 리뷰는 입력 길이와 모델 상태에 따라 수십 초 이상 걸릴 수 있으므로 HTTP 요청 안에서 동기 처리하지 않습니다. 사용자는 리뷰 요청 후 `review_id`를 받고, 이후 상태 조회 API로 `pending`, `processing`, `completed`, `failed` 상태를 확인합니다.

### Vector Store

PostgreSQL은 일반 관계형 데이터와 벡터 데이터를 함께 저장합니다.

사용자, 프로젝트, 업로드 파일, 코드 청크, 리뷰, 대화, 메시지 메타데이터를 관리하고, `pgvector`를 통해 코드 청크 임베딩의 코사인 유사도 검색을 수행합니다. PostgreSQL은 원본 데이터와 벡터의 기준 저장소이며, 프로젝트/사용자 권한 필터링의 기준이 됩니다.

### Observability

Elasticsearch는 운영 관측성과 코드 전문검색을 함께 담당합니다.

API 요청, LLM 호출, RAG 검색, 웹 검색, 장애 로그를 구조화해 Elasticsearch에 저장합니다. Kibana에서는 `codereview-*` data view를 만들어 처리 시간, 실패율, 요청 흐름, 모델 호출 현황을 확인할 수 있습니다.

또한 코드 청크를 `codereview-code-chunks` 인덱스에 색인해 함수명, 파일명, 에러 문자열, 식별자처럼 정확한 키워드가 중요한 검색을 담당합니다.

Kibana는 Elasticsearch 확인 화면을 담당합니다. `codereview-*` 로그 인덱스와 `codereview-code-chunks` 코드 검색 인덱스를 data view로 등록하면 Discover에서 문서, 필드, 쿼리 결과를 확인할 수 있고, 필요하면 대시보드로 처리 시간과 실패율을 시각화할 수 있습니다.

### Hybrid Retrieval

RAG 검색은 `pgvector`와 Elasticsearch 결과를 함께 사용합니다.

`pgvector`는 질문과 의미적으로 가까운 코드 청크를 찾고, Elasticsearch는 BM25 기반으로 정확한 키워드와 파일명, 함수명, 에러 문자열을 찾습니다. 애플리케이션 retriever는 두 결과를 RRF 방식으로 합치며, 기본 가중치는 Elasticsearch `1.25`, pgvector `1.0`으로 설정해 정확한 식별자 검색 범위를 조금 더 넓게 잡습니다.

### Local Models

Ollama는 로컬 모델 실행 계층입니다.

`qwen3` 계열 모델은 리뷰와 답변 생성을 담당하고, `nomic-embed-text`는 코드 청크와 사용자 질문을 벡터로 변환합니다. 이미지가 포함된 요청에서는 `llava`가 화면 상태나 에러 이미지를 먼저 텍스트로 설명하고, 그 설명을 다시 코드 검색과 답변 생성에 사용합니다.

---

## 5. 내역

### 주요 기능

#### 인증과 사용자 세션

이메일/패스워드 기반 회원가입과 로그인을 지원합니다. 인증은 JWT Access Token과 Refresh Token으로 구성되며, Refresh Token은 Redis에 저장해 세션 상태를 관리합니다.

#### 코드 업로드와 파싱

단일 소스 파일 업로드와 zip 프로젝트 업로드를 지원합니다. 업로드된 코드는 Tree-sitter를 통해 Python, JavaScript, Java 기준으로 파싱되며, 함수, 클래스, 모듈 단위의 코드 청크로 분리됩니다.

#### 임베딩과 벡터 검색

코드 청크는 Ollama `nomic-embed-text` 모델로 임베딩됩니다. 생성된 벡터는 PostgreSQL/pgvector에 저장되고, 같은 청크는 Elasticsearch에도 색인됩니다. 검색 시에는 pgvector 의미 검색과 Elasticsearch BM25 검색 결과를 합쳐 관련 코드 컨텍스트를 찾습니다.

#### 코드 리뷰와 RAG 답변

Ollama `qwen3` 계열 모델을 사용해 코드 리뷰, 일반 채팅, 프로젝트 기반 RAG Q&A를 제공합니다. 파일 리뷰는 Celery와 Redis를 통해 비동기 작업으로 처리하고, 프로젝트 질문은 검색된 코드 청크를 함께 전달해 답변을 생성합니다.

#### 대화와 스트리밍

대화 내역 저장, 메시지 브랜칭, 응답 재생성, 소프트 삭제를 지원합니다. 긴 LLM 응답은 SSE로 스트리밍하며, Think 모드에서는 모델의 생각 영역과 실제 답변을 분리해 표시합니다.

#### 멀티모달과 웹 검색

이미지와 프로젝트 코드를 함께 사용하는 멀티모달 RAG를 지원합니다. 이미지 분석 결과를 코드 검색 질의로 연결하고, 필요할 경우 웹 검색 결과를 답변 컨텍스트에 추가합니다.

#### 참조와 운영 로그

RAG 답변에는 참조된 코드 파일, 청크 타입, 라인 정보를 표시합니다. 관리자 로그 뷰어를 통해 실시간 요청 흐름을 확인할 수 있으며, Elasticsearch에는 API 요청, LLM 호출, RAG 검색, 웹 검색 이벤트가 장기 검색 가능한 로그로 저장됩니다.

#### 모델 설정

고급 모델 설정 패널을 통해 샘플링, 반복 제어, 생성 길이, 하드웨어, RAG, 웹 검색 관련 파라미터를 조정할 수 있습니다.

### 기술 스택

| 영역                     | 기술                                  |
| ------------------------ | ------------------------------------- |
| Frontend                 | Next.js, React, Tailwind CSS          |
| Backend                  | FastAPI, SQLAlchemy asyncio, Pydantic |
| Async Worker             | Celery                                |
| Broker / Cache / Session | Redis                                 |
| Database                 | PostgreSQL, pgvector                  |
| Local LLM                | Ollama, qwen3                         |
| Embedding                | Ollama, nomic-embed-text              |
| Vision Model             | Ollama, llava                         |
| Code Parsing             | Tree-sitter                           |
| Log / Search             | Elasticsearch, Kibana                 |
| Infra                    | Docker Compose                        |

### 주요 데이터 흐름

```text
파일 업로드
  -> 언어 감지
  -> Tree-sitter 파싱
  -> 코드 청킹
  -> Ollama 임베딩
  -> PostgreSQL/pgvector 저장
  -> 자연어 검색
  -> 관련 코드 컨텍스트 추출
  -> LLM 답변 생성
  -> UI 표시
```

---

## 6. 시나리오

시나리오 검증용 예시 파일은 [`test/scenario_temp_auth.py`](test/scenario_temp_auth.py)에 분리해 두었습니다.

### 시나리오 1: 프로젝트 업로드 후 코드 기반 Q&A

사용자는 인증/권한 처리 코드가 포함된 프로젝트를 zip 형태로 업로드합니다.

백엔드는 압축을 해제하고 지원 가능한 소스 파일을 필터링합니다. 이후 Tree-sitter가 코드를 함수, 클래스, 모듈 단위로 파싱하고, 각 코드 청크는 `nomic-embed-text` 모델로 임베딩됩니다.

임베딩 벡터와 코드 메타데이터는 PostgreSQL/pgvector에 저장되고, 코드 청크 전문은 Elasticsearch에도 색인됩니다. 사용자가 “관리자 권한 검사가 제대로 분리되어 있는지 확인해줘”라고 질문하면, 시스템은 질문을 임베딩해 의미적으로 가까운 코드를 찾는 동시에 Elasticsearch에서 `admin`, `permission`, `require_admin` 같은 키워드 기반 결과를 찾습니다.

검색된 코드 컨텍스트는 LLM에 전달되고, UI는 답변과 함께 참조된 파일, 청크 타입, 라인 정보를 표시합니다.

이 시나리오에서 확인하려는 것은 LLM이 막연한 보안 조언을 하는지가 아니라, 실제 업로드된 코드에서 `login`, `require_admin`, `delete_user` 같은 함수 경계를 찾아 설명할 수 있는지입니다.

### 시나리오 2: 이미지와 코드 컨텍스트를 함께 사용한 문제 분석

사용자는 권한 오류 화면 또는 관리자 기능 실패 화면 이미지를 업로드합니다.

Vision 모델은 이미지를 분석해 화면 상태와 문제 단서를 텍스트로 요약합니다. 시스템은 이미지 설명과 사용자 질문을 기반으로 프로젝트 코드에서 관련 청크를 검색합니다.

검색된 코드와 이미지 분석 결과는 LLM에 함께 전달됩니다. 이후 시스템은 문제 원인, 관련 파일, 수정 방향을 답변합니다.

필요한 경우 웹 검색을 함께 사용해 라이브러리 오류, 프레임워크 변경사항, 외부 문서 정보를 보강할 수 있습니다. 관리자 로그 뷰어에서는 요청 흐름과 에러 로그를 확인할 수 있습니다.

이 시나리오에서는 이미지 분석 결과가 코드 검색 질의로 이어지는 흐름을 확인합니다. 예를 들어 “permission denied” 화면이 들어오면, 시스템은 권한 검사와 관련된 코드 청크를 찾고 `require_admin` 또는 관리자 API 보호 흐름을 중심으로 원인을 설명해야 합니다.

---

## 7. 결과

이 프로젝트를 통해 로컬 환경에서 코드 리뷰와 프로젝트 질의응답이 가능한 AI 개발 보조 파이프라인을 구성했습니다.

구현 결과는 다음과 같습니다.

- 업로드된 코드를 구조적으로 파싱하고 벡터화할 수 있습니다.
- 자연어 질문으로 프로젝트 내부 코드를 hybrid 검색할 수 있습니다.
- 검색된 코드 컨텍스트를 기반으로 LLM 답변을 생성할 수 있습니다.
- zip 프로젝트 업로드 후 project_id 기준 RAG Q&A 답변을 생성할 수 있습니다.
- 파일 리뷰는 Celery를 통해 비동기로 처리할 수 있습니다.
- 긴 LLM 응답은 SSE로 스트리밍할 수 있습니다.
- 이미지, 웹 검색, RAG 참조를 결합한 복합 분석 흐름을 지원합니다.
- 관리자 화면에서 실시간 로그를 확인할 수 있습니다.

현재 Elasticsearch/Kibana는 Docker Compose에 연결되어 있으며, 백엔드는 `codereview-*` 인덱스에 API 요청, LLM 호출, RAG 검색, 웹 검색 이벤트를 기록합니다. 코드 청크는 `codereview-code-chunks` 인덱스에 저장되어 RAG와 일반 코드 검색의 BM25 검색 신호로 사용됩니다. 단일 노드 로컬 환경에서는 `number_of_replicas=0`으로 인덱스를 생성해 클러스터 health가 불필요하게 `yellow`가 되지 않도록 구성했습니다.

Elasticsearch 확인 화면은 Kibana로 통합합니다. Kibana는 `http://localhost:5601`에서 로그 탐색, data view, 대시보드 구성, 코드 청크 인덱스 확인을 담당합니다.

---

## 8. 검증 현황

검증은 긴 E2E 한 번으로 처리하지 않고, 각 기능을 짧은 단위로 나누어 확인했습니다. 프로그램 기동, 재시작, 검증 명령은 40초 이내 실행을 원칙으로 두고, 이를 넘기면 실패로 판정한 뒤 원인을 분리했습니다.

| 검증 항목 | 상태 | 확인 내용 |
| --- | --- | --- |
| 인프라 기동 | 통과 | PostgreSQL, Redis, Elasticsearch, Kibana 기동 및 health 확인 |
| 기본 앱 상태 | 통과 | Next.js, FastAPI, Ollama 포트 및 HTTP 응답 확인 |
| Kibana data view | 통과 | 운영 로그용 data view와 코드 청크용 data view 생성 |
| 일반 LLM 채팅 | 통과 | `POST /api/v1/chat/` 응답 생성 및 `llm-call` 로그 적재 확인 |
| 단일 파일 업로드 | 통과 | `.py` 파일 업로드, 5개 함수 청크 생성, pgvector 저장, Elasticsearch 색인 확인 |
| 코드 검색 | 통과 | `asyncio create_task price` 질의에서 관련 함수 청크 반환 확인 |
| 프로젝트 zip 업로드 | 통과 | 2개 파일 zip 업로드, project_id 생성, 8개 청크 생성 및 색인 확인 |
| 프로젝트 RAG Q&A | 통과 | project_id 기준 검색 후 `save_order`의 async task 미 await 문제를 답변으로 생성 |
| 운영 로그 적재 | 통과 | API request, RAG search, LLM call 로그가 Elasticsearch/Kibana에서 조회됨 |

프로젝트 RAG Q&A 검증 예시는 다음과 같습니다.

```text
질문:
why is save_order price often zero?

응답:
The `price` is often zero because the `calculate_price` task is scheduled but never awaited, so the `price` variable remains uninitialized.
```

검증 시 `top_k=3`, 긴 답변 설정에서는 로컬 모델 응답이 제한 시간을 넘길 수 있었습니다. 최종 검증은 `top_k=1`, 짧은 답변 설정으로 수행했으며 33.5초에 통과했습니다. 이 결과는 로컬 모델 환경에서는 검색 범위, 출력 길이, timeout 설정이 사용자 경험과 안정성에 직접적인 영향을 준다는 점을 보여줍니다.

짧은 구성요소 검증은 다음 명령으로 실행합니다. 이 스크립트는 LLM 생성, 파일 업로드, 긴 E2E 시나리오를 실행하지 않고 포트와 HTTP 상태만 세분화해 확인합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-components.ps1
```

---

## 9. 실행 방법

### 사전 준비

- Docker Desktop
- Python 3.10 이상
- Node.js 20 이상
- Ollama
- Ollama 모델: `qwen3:8b`, `nomic-embed-text`, `llava:7b`

### 환경 변수

루트의 `.env.example`을 복사해 `.env`를 만든 뒤 로컬 환경에 맞게 수정합니다.

```powershell
Copy-Item .env.example .env
```

공개 저장소에는 실제 `.env`를 올리지 않습니다. `.env`에는 DB 비밀번호, JWT secret, 관리자 초기 비밀번호가 포함될 수 있습니다.

### 실행

```bat
start.bat
```

실행 후 접속 주소는 다음과 같습니다.

| 화면 | URL |
| --- | --- |
| App UI | `http://localhost:3000` |
| FastAPI | `http://localhost:8000` |
| Swagger | `http://localhost:8000/docs` |
| Elasticsearch | `http://localhost:9200` |
| Kibana | `http://localhost:5601` |

### 종료

```bat
stop.bat --all --no-pause
```

### 짧은 상태 확인

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-components.ps1
```

이 스크립트는 긴 E2E나 LLM 생성을 실행하지 않고, 포트와 HTTP 상태만 확인합니다. 각 실행/검증은 40초를 넘기지 않는 것을 원칙으로 합니다.

### Kibana 확인

Kibana에서는 다음 data view를 만들면 로그와 코드 청크를 확인할 수 있습니다.

| Data view | Index pattern | Time field |
| --- | --- | --- |
| CodeReview Operational Logs | `codereview-api-*`, `codereview-llm-*`, `codereview-rag-*`, `codereview-web-search-*` | `@timestamp` |
| CodeReview Code Chunks | `codereview-code-chunks` | 없음 |

---

## 10. 얻은 점

로컬 LLM을 사용하면서 모델 호출 자체보다 주변 파이프라인이 더 중요하다는 점을 느꼈습니다. 모델에 코드를 그대로 전달하는 방식은 작은 예제에서는 동작하지만, 프로젝트 단위 코드에서는 필요한 맥락을 찾는 과정이 먼저 필요했습니다. Tree-sitter로 코드를 청킹하고 임베딩과 pgvector 검색을 붙였을 때, 답변이 훨씬 코드 기반으로 바뀌는 것을 확인할 수 있었습니다.

PostgreSQL/pgvector를 사용하면서 벡터 검색을 별도 시스템으로 분리하지 않고 기존 관계형 데이터와 함께 관리하는 장점을 느꼈습니다. 파일, 프로젝트, 청크, 사용자 정보를 SQL 관계로 관리하면서도 같은 DB 안에서 유사도 검색을 수행할 수 있었습니다. 이 구조는 작은 로컬 AI 도구를 만들 때 인프라 복잡도를 줄이는 데 유리했습니다.

Celery와 Redis를 사용하면서 LLM 작업을 HTTP 요청과 분리해야 하는 이유를 체감했습니다. 코드 리뷰 생성은 모델 크기와 입력 길이에 따라 시간이 크게 달라졌고, 이를 동기 API로 처리하면 사용자 경험과 서버 안정성이 모두 나빠질 수 있었습니다. 비동기 큐를 사용하니 리뷰 요청, 상태 조회, 결과 저장 흐름을 더 명확히 나눌 수 있었습니다.

SSE 스트리밍을 구현하면서 LLM 응답은 “완료 후 한 번에 받는 데이터”보다 “생성 중인 상태를 계속 전달하는 데이터”에 가깝다는 점을 느꼈습니다. 스트리밍을 붙이니 긴 답변에서도 사용자가 기다리는 시간을 덜 답답하게 느낄 수 있었고, Think 모드나 RAG 참조 이벤트처럼 토큰 외의 상태 이벤트도 함께 전달할 수 있었습니다.

이미지 분석과 코드 RAG를 결합하면서 멀티모달 기능은 단순히 이미지를 설명하는 데서 끝나면 부족하다는 점을 느꼈습니다. 이미지에서 얻은 단서를 코드 검색 질의로 연결해야 실제 개발 문제 해결에 가까워졌습니다. 화면 상태, 에러 메시지, 관련 코드 청크가 하나의 답변 컨텍스트로 합쳐질 때 문제 분석의 폭이 넓어졌습니다.

Elasticsearch를 붙이는 과정에서는 AI 기능도 운영 관측성이 필요하다는 점을 확인했습니다. LLM 호출 시간, 임베딩 처리 시간, RAG 검색 결과 수, 실패한 API를 기록하지 않으면 문제가 생겼을 때 원인을 찾기 어렵습니다. 따라서 Elasticsearch는 벡터 저장소가 아니라, 로컬 AI 시스템이 어떻게 동작했는지 추적하는 운영 로그 계층으로 두는 것이 적절하다고 판단했습니다.

전체적으로 이 프로젝트를 진행하면서 로컬 AI 개발 도구는 모델, 데이터베이스, 비동기 처리, 스트리밍, 로그가 함께 맞물려야 실제 사용 가능한 형태가 된다는 점을 얻었습니다.
