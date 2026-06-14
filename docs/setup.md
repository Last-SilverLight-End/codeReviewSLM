# 로컬 설치 및 실행

이 문서는 Local AI Code Review Platform을 로컬 Windows 환경에서 실행하기 위한 설치 절차를 정리합니다.

## 사전 준비

다음 프로그램이 로컬 PC에 설치되어 있어야 합니다.

| 항목 | 권장 버전 / 용도 |
| --- | --- |
| Docker Desktop | PostgreSQL, Redis, Elasticsearch, Kibana 실행 |
| Python | 3.10 이상, FastAPI 백엔드 실행 |
| Node.js | 20 이상, Next.js 프론트엔드 실행 |
| Ollama | 로컬 LLM, 임베딩, 이미지 분석 모델 실행 |
| Git | 저장소 복제 |

Ollama는 Docker 컨테이너가 아니라 Windows 네이티브 프로세스로 실행합니다. Docker Compose는 PostgreSQL, Redis, Elasticsearch, Kibana만 실행합니다.

## 저장소 복제

```powershell
git clone https://github.com/Last-SilverLight-End/codeReviewSLM.git
cd codeReviewSLM
```

## 환경 변수 설정

루트의 `.env.example`을 복사해 `.env`를 만든 뒤 로컬 환경에 맞게 수정합니다.

```powershell
Copy-Item .env.example .env
```

최소 확인 항목은 다음과 같습니다.

| 변수 | 설명 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL 접속 문자열. 기본 포트는 `5433` |
| `JWT_SECRET_KEY` | 로컬에서 사용할 긴 랜덤 문자열 |
| `ADMIN_EMAIL` | 관리자 계정 생성 시 사용할 이메일 |
| `ADMIN_PASSWORD` | 관리자 계정 생성 시 사용할 비밀번호 |
| `OLLAMA_BASE_URL` | 기본값 `http://localhost:11434` |
| `OLLAMA_LLM_MODEL` | 기본값 `qwen3:8b` |
| `OLLAMA_EMBED_MODEL` | 기본값 `nomic-embed-text` |
| `OLLAMA_VISION_MODEL` | 기본값 `llava:7b` |

공개 저장소에는 실제 `.env`를 올리지 않습니다. `.env`에는 DB 비밀번호, JWT secret, 관리자 초기 비밀번호가 포함될 수 있습니다.

## Ollama 모델 준비

Ollama를 실행한 뒤 필요한 모델을 내려받습니다.

```powershell
ollama pull qwen3:8b
ollama pull nomic-embed-text
ollama pull llava:7b
```

모델 목록은 다음 명령으로 확인할 수 있습니다.

```powershell
ollama list
```

## 백엔드 의존성 설치

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
cd ..
```

## 프론트엔드 의존성 설치

```powershell
cd frontend
npm install
cd ..
```

## 데이터베이스 마이그레이션

Docker 인프라를 먼저 실행한 뒤 Alembic 마이그레이션을 적용합니다.

```powershell
docker compose up -d

cd backend
.\venv\Scripts\activate
alembic upgrade head
cd ..
```

관리자 계정이 필요하면 `.env`의 `ADMIN_EMAIL`, `ADMIN_PASSWORD`를 설정한 뒤 실행합니다.

```powershell
cd backend
.\venv\Scripts\activate
python create_admin.py
cd ..
```

## 전체 실행

루트에서 실행합니다.

```bat
start.bat
```

`start.bat`은 Docker 인프라, Ollama 포트 확인, FastAPI, Celery worker, Next.js를 순서대로 확인합니다. 각 실행 단계는 40초 이내 동작을 기준으로 하며, 오래 걸리는 경우 실패로 보고 원인을 분리하도록 구성되어 있습니다.

실행 후 접속 주소는 다음과 같습니다.

| 화면 | URL |
| --- | --- |
| App UI | `http://localhost:3000` |
| FastAPI | `http://localhost:8000` |
| Swagger | `http://localhost:8000/docs` |
| Elasticsearch | `http://localhost:9200` |
| Kibana | `http://localhost:5601` |

## 짧은 상태 확인

긴 E2E나 LLM 생성을 실행하지 않고, 포트와 HTTP 상태만 빠르게 확인합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-components.ps1
```

## 종료

앱 프로세스와 Docker 인프라를 함께 종료합니다.

```bat
stop.bat --all --no-pause
```

## Kibana 확인

Kibana에서는 다음 data view를 만들면 로그와 코드 청크를 확인할 수 있습니다.

| Data view | Index pattern | Time field |
| --- | --- | --- |
| CodeReview Operational Logs | `codereview-api-*`, `codereview-llm-*`, `codereview-rag-*`, `codereview-web-search-*` | `@timestamp` |
| CodeReview Code Chunks | `codereview-code-chunks` | 없음 |

## 실행 문제 확인

실행이 되지 않으면 먼저 짧은 상태 확인 스크립트로 어느 구성요소가 실패했는지 확인합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-components.ps1
```

자주 확인할 지점은 다음과 같습니다.

| 증상 | 확인 지점 |
| --- | --- |
| 로그인에서 `Failed to fetch` | FastAPI `8000` 포트 실행 여부 |
| RAG 답변이 느림 | Ollama 모델 상태, `top_k`, 출력 길이, timeout 설정 |
| 파일 업로드 실패 | 지원 확장자 `.py`, `.js`, `.ts`, `.java` 여부 |
| Kibana 접속 실패 | Docker Compose에서 Kibana 컨테이너 상태 |
| DB 연결 실패 | PostgreSQL 호스트 포트 `5433` 사용 여부 |
