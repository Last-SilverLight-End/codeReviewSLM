# 프로젝트 설명

Local AI Code Review Platform은 로컬 개발 환경에서 코드 리뷰, 코드 검색, 프로젝트 질의응답, 이미지 기반 문제 분석을 지원하는 AI 시스템입니다.

사용자가 단일 소스 파일을 업로드하면 시스템은 해당 파일을 파싱하고 로컬 LLM으로 리뷰를 생성합니다. zip 프로젝트를 업로드하면 여러 소스 파일을 함수, 클래스, 모듈 단위로 청킹하고, 각 청크를 임베딩해 벡터 검색 가능한 지식 베이스로 저장합니다.

이후 사용자는 자연어로 프로젝트에 대해 질문할 수 있습니다. 시스템은 질문과 관련된 코드 청크를 PostgreSQL/pgvector의 의미 검색과 Elasticsearch의 BM25 전문검색으로 함께 찾고, 합쳐진 코드 컨텍스트를 LLM에 전달해 실제 코드에 근거한 답변을 생성합니다.

## 목적

이 프로젝트의 목적은 개발 과정에서 반복적으로 발생하는 코드 이해, 리뷰, 디버깅, 변경 영향 분석을 로컬 AI 시스템으로 지원하는 것입니다.

주요 목표는 다음과 같습니다.

- 프로젝트 코드를 업로드하고 검색 가능한 코드 지식 베이스로 변환합니다.
- 로컬 LLM을 사용해 코드 리뷰와 개발 질문에 대한 답변을 생성합니다.
- RAG 구조를 통해 답변이 실제 프로젝트 코드에 근거하도록 만듭니다.
- 이미지, 로그, 웹 검색 결과를 함께 활용해 문제 분석 범위를 넓힙니다.
- 비동기 작업, 스트리밍 응답, 로그 관측성을 포함한 운영 가능한 AI 개발 도구 구조를 실험합니다.

## 아키텍처

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

## 시스템 구조

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

### Hybrid Retrieval

RAG 검색은 `pgvector`와 Elasticsearch 결과를 함께 사용합니다.

`pgvector`는 질문과 의미적으로 가까운 코드 청크를 찾고, Elasticsearch는 BM25 기반으로 정확한 키워드와 파일명, 함수명, 에러 문자열을 찾습니다. 애플리케이션 retriever는 두 결과를 RRF 방식으로 합치며, 기본 가중치는 Elasticsearch `1.25`, pgvector `1.0`으로 설정해 정확한 식별자 검색 범위를 조금 더 넓게 잡습니다.

### Local Models

Ollama는 로컬 모델 실행 계층입니다.

`qwen3` 계열 모델은 리뷰와 답변 생성을 담당하고, `nomic-embed-text`는 코드 청크와 사용자 질문을 벡터로 변환합니다. 이미지가 포함된 요청에서는 `llava`가 화면 상태나 에러 이미지를 먼저 텍스트로 설명하고, 그 설명을 다시 코드 검색과 답변 생성에 사용합니다.

## 주요 기능

### 인증과 사용자 세션

이메일/패스워드 기반 회원가입과 로그인을 지원합니다. 인증은 JWT Access Token과 Refresh Token으로 구성되며, Refresh Token은 Redis에 저장해 세션 상태를 관리합니다.

### 코드 업로드와 파싱

단일 소스 파일 업로드와 zip 프로젝트 업로드를 지원합니다. 업로드된 코드는 Tree-sitter를 통해 Python, JavaScript, Java 기준으로 파싱되며, 함수, 클래스, 모듈 단위의 코드 청크로 분리됩니다.

### 임베딩과 벡터 검색

코드 청크는 Ollama `nomic-embed-text` 모델로 임베딩됩니다. 생성된 벡터는 PostgreSQL/pgvector에 저장되고, 같은 청크는 Elasticsearch에도 색인됩니다. 검색 시에는 pgvector 의미 검색과 Elasticsearch BM25 검색 결과를 합쳐 관련 코드 컨텍스트를 찾습니다.

### 코드 리뷰와 RAG 답변

Ollama `qwen3` 계열 모델을 사용해 코드 리뷰, 일반 채팅, 프로젝트 기반 RAG Q&A를 제공합니다. 파일 리뷰는 Celery와 Redis를 통해 비동기 작업으로 처리하고, 프로젝트 질문은 검색된 코드 청크를 함께 전달해 답변을 생성합니다.

### 대화와 스트리밍

대화 내역 저장, 메시지 브랜칭, 응답 재생성, 소프트 삭제를 지원합니다. 긴 LLM 응답은 SSE로 스트리밍하며, Think 모드에서는 모델의 생각 영역과 실제 답변을 분리해 표시합니다.

### 멀티모달과 웹 검색

이미지와 프로젝트 코드를 함께 사용하는 멀티모달 RAG를 지원합니다. 이미지 분석 결과를 코드 검색 질의로 연결하고, 필요할 경우 웹 검색 결과를 답변 컨텍스트에 추가합니다.

### 참조와 운영 로그

RAG 답변에는 참조된 코드 파일, 청크 타입, 라인 정보를 표시합니다. 관리자 로그 뷰어를 통해 실시간 요청 흐름을 확인할 수 있으며, Elasticsearch에는 API 요청, LLM 호출, RAG 검색, 웹 검색 이벤트가 장기 검색 가능한 로그로 저장됩니다.

## 주요 데이터 흐름

```text
파일 업로드
  -> 언어 감지
  -> Tree-sitter 파싱
  -> 코드 청킹
  -> Ollama 임베딩
  -> PostgreSQL/pgvector 저장
  -> Elasticsearch 코드 청크 색인
  -> hybrid 검색
  -> 관련 코드 컨텍스트 추출
  -> LLM 답변 생성
  -> UI 표시
```

## 시나리오

### 시나리오 1: 프로젝트 업로드 후 코드 기반 Q&A

사용자는 인증/권한 처리 코드가 포함된 프로젝트를 zip 형태로 업로드합니다.

백엔드는 압축을 해제하고 지원 가능한 소스 파일을 필터링합니다. 이후 Tree-sitter가 코드를 함수, 클래스, 모듈 단위로 파싱하고, 각 코드 청크는 `nomic-embed-text` 모델로 임베딩됩니다.

임베딩 벡터와 코드 메타데이터는 PostgreSQL/pgvector에 저장되고, 코드 청크 전문은 Elasticsearch에도 색인됩니다. 사용자가 “관리자 권한 검사가 제대로 분리되어 있는지 확인해줘”라고 질문하면, 시스템은 질문을 임베딩해 의미적으로 가까운 코드를 찾는 동시에 Elasticsearch에서 `admin`, `permission`, `require_admin` 같은 키워드 기반 결과를 찾습니다.

검색된 코드 컨텍스트는 LLM에 전달되고, UI는 답변과 함께 참조된 파일, 청크 타입, 라인 정보를 표시합니다.

### 시나리오 2: 이미지와 코드 컨텍스트를 함께 사용한 문제 분석

사용자는 권한 오류 화면 또는 관리자 기능 실패 화면 이미지를 업로드합니다.

Vision 모델은 이미지를 분석해 화면 상태와 문제 단서를 텍스트로 요약합니다. 시스템은 이미지 설명과 사용자 질문을 기반으로 프로젝트 코드에서 관련 청크를 검색합니다.

검색된 코드와 이미지 분석 결과는 LLM에 함께 전달됩니다. 이후 시스템은 문제 원인, 관련 파일, 수정 방향을 답변합니다.

필요한 경우 웹 검색을 함께 사용해 라이브러리 오류, 프레임워크 변경사항, 외부 문서 정보를 보강할 수 있습니다. 관리자 로그 뷰어에서는 요청 흐름과 에러 로그를 확인할 수 있습니다.
