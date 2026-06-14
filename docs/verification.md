# 검증 현황

검증은 긴 E2E 한 번으로 처리하지 않고, 각 기능을 짧은 단위로 나누어 확인했습니다. 프로그램 기동, 재시작, 검증 명령은 40초 이내 실행을 원칙으로 두고, 이를 넘기면 실패로 판정한 뒤 원인을 분리했습니다.

## 검증 결과

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

## RAG Q&A 검증 예시

```text
질문:
why is save_order price often zero?

응답:
The `price` is often zero because the `calculate_price` task is scheduled but never awaited, so the `price` variable remains uninitialized.
```

검증 시 `top_k=3`, 긴 답변 설정에서는 로컬 모델 응답이 제한 시간을 넘길 수 있었습니다. 최종 검증은 `top_k=1`, 짧은 답변 설정으로 수행했으며 33.5초에 통과했습니다. 이 결과는 로컬 모델 환경에서는 검색 범위, 출력 길이, timeout 설정이 사용자 경험과 안정성에 직접적인 영향을 준다는 점을 보여줍니다.

## 짧은 구성요소 검증

다음 스크립트는 LLM 생성, 파일 업로드, 긴 E2E 시나리오를 실행하지 않고 포트와 HTTP 상태만 세분화해 확인합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-components.ps1
```
