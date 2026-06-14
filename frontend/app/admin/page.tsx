"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

import { BASE_URL } from "@/lib/api";

const MAX_LOGS_IN_MEMORY = 1000;
const LOG_RECONNECT_DELAY_MS = 3000;
const SCROLL_AT_BOTTOM_THRESHOLD_PX = 60;
const OBSERVABILITY_REFRESH_MS = 10000;

type LogEntry = {
  ts: string;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  source: string;
  msg: string;
};

type ServiceStatus = {
  name: string;
  url: string;
  ok: boolean;
  status: string;
  detail: Record<string, unknown> | string | null;
};

type IndexRow = {
  health: string;
  status: string;
  index: string;
  docs_count: number;
  store_size: string;
};

type RecentEvent = {
  index: string;
  timestamp: string;
  event_type: string;
  route?: string | null;
  method?: string | null;
  path?: string | null;
  status_code?: number | null;
  duration_ms?: number | null;
  model?: string | null;
  purpose?: string | null;
  tokens_input?: number | null;
  tokens_output?: number | null;
  project_id?: number | null;
  top_k?: number | null;
  result_count?: number | null;
  filenames?: string[];
  error?: string | null;
};

type ObservabilitySnapshot = {
  generated_at: string;
  kibana_url: string;
  services: {
    elasticsearch: ServiceStatus;
    kibana: ServiceStatus;
  };
  summary: {
    recent_event_count: number;
    recent_error_count: number;
    recent_rag_count: number;
    recent_llm_count: number;
    index_count: number;
    code_chunk_docs: number;
  };
  indexes: IndexRow[];
  recent_events: RecentEvent[];
};

const LEVEL_STYLE: Record<string, string> = {
  DEBUG: "text-zinc-500",
  INFO: "text-emerald-400",
  WARNING: "text-yellow-400",
  ERROR: "text-red-400",
  CRITICAL: "text-red-300 font-bold",
};

const LEVEL_BADGE: Record<string, string> = {
  DEBUG: "bg-zinc-700 text-zinc-300",
  INFO: "bg-emerald-900/60 text-emerald-300",
  WARNING: "bg-yellow-900/60 text-yellow-300",
  ERROR: "bg-red-900/60 text-red-300",
  CRITICAL: "bg-red-800 text-red-100",
};

const SOURCE_BADGE: Record<string, string> = {
  HTTP: "bg-blue-900/50 text-blue-300",
  LLM: "bg-purple-900/50 text-purple-300",
  APP: "bg-indigo-900/50 text-indigo-300",
  SQL: "bg-orange-900/50 text-orange-300",
  UVICORN: "bg-zinc-700 text-zinc-400",
  FASTAPI: "bg-zinc-700 text-zinc-400",
};

const EVENT_BADGE: Record<string, string> = {
  "api-request": "bg-blue-500/10 text-blue-300 border-blue-500/20",
  "llm-call": "bg-purple-500/10 text-purple-300 border-purple-500/20",
  "rag-search": "bg-indigo-500/10 text-indigo-300 border-indigo-500/20",
  "web-search": "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",
};

const ALL_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];
const ALL_SOURCES = ["HTTP", "APP", "LLM", "SQL", "UVICORN", "FASTAPI"];

function formatTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString("ko-KR", { hour12: false });
}

function serviceDetail(service: ServiceStatus) {
  if (!service.detail || typeof service.detail === "string") return service.detail ?? "";
  return Object.entries(service.detail)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => `${key}: ${value}`)
    .join(" / ");
}

function HealthDot({ ok }: { ok: boolean }) {
  return <span className={`h-2.5 w-2.5 rounded-full ${ok ? "bg-emerald-400" : "bg-red-400"}`} />;
}

function SectionTitle({ title, right }: { title: string; right?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-white/10 px-4 py-2.5">
      <h2 className="text-sm font-semibold text-zinc-200">{title}</h2>
      {right}
    </div>
  );
}

export default function AdminPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [filterLevel, setFilterLevel] = useState<string[]>(["INFO", "WARNING", "ERROR", "CRITICAL"]);
  const [filterSource, setFilterSource] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [snapshot, setSnapshot] = useState<ObservabilitySnapshot | null>(null);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectRef = useRef<() => void>(() => {});
  const mountedRef = useRef(false);

  const loadObservability = useCallback(async () => {
    try {
      const res = await fetch(`${BASE_URL}/admin/observability`, { cache: "no-store" });
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      setSnapshot(data);
      setSnapshotError(null);
    } catch (err) {
      setSnapshotError(err instanceof Error ? err.message : "관측 데이터 로딩 실패");
    }
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (esRef.current) esRef.current.close();
    const es = new EventSource(`${BASE_URL}/admin/logs/stream`);
    esRef.current = es;

    es.onopen = () => setConnected(true);
    es.onmessage = (e) => {
      try {
        const entry: LogEntry = JSON.parse(e.data);
        setLogs((prev) => {
          const next = [...prev, entry];
          return next.length > MAX_LOGS_IN_MEMORY ? next.slice(-MAX_LOGS_IN_MEMORY) : next;
        });
      } catch {
        /* skip */
      }
    };
    es.onerror = () => {
      if (!mountedRef.current) return;
      setConnected(false);
      es.close();
      reconnectTimerRef.current = setTimeout(() => {
        connectRef.current();
      }, LOG_RECONNECT_DELAY_MS);
    };
  }, []);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      esRef.current?.close();
      esRef.current = null;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    };
  }, [connect]);

  useEffect(() => {
    void Promise.resolve().then(loadObservability);
    const timer = setInterval(loadObservability, OBSERVABILITY_REFRESH_MS);
    return () => clearInterval(timer);
  }, [loadObservability]);

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, autoScroll]);

  function handleScroll() {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_AT_BOTTOM_THRESHOLD_PX;
    setAutoScroll(atBottom);
  }

  async function handleClear() {
    await fetch(`${BASE_URL}/admin/logs`, { method: "DELETE" });
    setLogs([]);
  }

  const filtered = logs.filter((log) => {
    if (filterLevel.length > 0 && !filterLevel.includes(log.level)) return false;
    if (filterSource.length > 0 && !filterSource.includes(log.source)) return false;
    if (search && !log.msg.toLowerCase().includes(search.toLowerCase()) && !log.source.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const recentRagEvents = useMemo(
    () => snapshot?.recent_events.filter((event) => event.event_type === "rag-search").slice(0, 6) ?? [],
    [snapshot],
  );
  const recentLlmEvents = useMemo(
    () => snapshot?.recent_events.filter((event) => event.event_type === "llm-call").slice(0, 6) ?? [],
    [snapshot],
  );

  function toggleLevel(level: string) {
    setFilterLevel((prev) => prev.includes(level) ? prev.filter((item) => item !== level) : [...prev, level]);
  }

  function toggleSource(source: string) {
    setFilterSource((prev) => prev.includes(source) ? prev.filter((item) => item !== source) : [...prev, source]);
  }

  return (
    <div className="min-h-screen bg-[#0d0d0d] text-white">
      <header className="sticky top-0 z-20 flex items-center gap-4 border-b border-white/10 bg-[#111]/95 px-5 py-3 backdrop-blur">
        <Link href="/" className="text-zinc-500 hover:text-white transition-colors" title="메인으로">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
        </Link>
        <div>
          <h1 className="text-sm font-semibold tracking-wide">Admin Observability</h1>
          <p className="text-xs text-zinc-600">API, RAG, LLM, Elasticsearch 로그 상태</p>
        </div>
        <div className="ml-auto flex items-center gap-3 text-xs">
          <span className={`flex items-center gap-1.5 ${connected ? "text-emerald-400" : "text-red-400"}`}>
            <HealthDot ok={connected} />
            {connected ? "Live logs" : "Log reconnecting"}
          </span>
          <button onClick={() => void loadObservability()}
            className="rounded border border-white/10 px-2 py-1 text-zinc-400 hover:border-white/20 hover:text-white">
            새로고침
          </button>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-7xl flex-col gap-4 px-4 py-4">
        {snapshotError && (
          <div className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            관측 데이터 로딩 실패: {snapshotError}
          </div>
        )}

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-md border border-white/10 bg-[#151515] p-4">
            <div className="flex items-center gap-2 text-sm text-zinc-400">
              <HealthDot ok={snapshot?.services.elasticsearch.ok ?? false} />
              Elasticsearch
            </div>
            <p className="mt-2 text-2xl font-semibold text-white">{snapshot?.services.elasticsearch.status ?? "loading"}</p>
            <p className="mt-1 truncate text-xs text-zinc-600">{snapshot ? serviceDetail(snapshot.services.elasticsearch) : "-"}</p>
          </div>
          <div className="rounded-md border border-white/10 bg-[#151515] p-4">
            <div className="flex items-center gap-2 text-sm text-zinc-400">
              <HealthDot ok={snapshot?.services.kibana.ok ?? false} />
              Kibana
            </div>
            <p className="mt-2 text-2xl font-semibold text-white">{snapshot?.services.kibana.status ?? "loading"}</p>
            <a href={snapshot?.kibana_url ?? "http://localhost:5601"} target="_blank" rel="noreferrer"
              className="mt-1 block truncate text-xs text-indigo-300 hover:text-indigo-200">
              {snapshot?.kibana_url ?? "http://localhost:5601"}
            </a>
          </div>
          <div className="rounded-md border border-white/10 bg-[#151515] p-4">
            <p className="text-sm text-zinc-400">최근 이벤트</p>
            <p className="mt-2 text-2xl font-semibold text-white">{snapshot?.summary.recent_event_count ?? 0}</p>
            <p className="mt-1 text-xs text-zinc-600">오류 {snapshot?.summary.recent_error_count ?? 0} / RAG {snapshot?.summary.recent_rag_count ?? 0} / LLM {snapshot?.summary.recent_llm_count ?? 0}</p>
          </div>
          <div className="rounded-md border border-white/10 bg-[#151515] p-4">
            <p className="text-sm text-zinc-400">색인 상태</p>
            <p className="mt-2 text-2xl font-semibold text-white">{snapshot?.summary.index_count ?? 0}</p>
            <p className="mt-1 text-xs text-zinc-600">코드 청크 문서 {snapshot?.summary.code_chunk_docs ?? 0}</p>
          </div>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-md border border-white/10 bg-[#141414]">
            <SectionTitle title="AI Pipeline" right={<span className="text-xs text-zinc-600">최근 갱신 {formatTime(snapshot?.generated_at)}</span>} />
            <div className="grid gap-3 p-4 md:grid-cols-5">
              {["API Request", "Hybrid RAG", "Ollama LLM", "Response", "Elasticsearch Log"].map((step, index) => (
                <div key={step} className="rounded border border-white/10 bg-[#101010] p-3">
                  <p className="text-xs text-zinc-600">Step {index + 1}</p>
                  <p className="mt-1 text-sm font-medium text-zinc-200">{step}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-md border border-white/10 bg-[#141414]">
            <SectionTitle title="Elasticsearch Indexes" />
            <div className="max-h-64 overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-[#141414] text-zinc-500">
                  <tr>
                    <th className="px-4 py-2 font-medium">index</th>
                    <th className="px-2 py-2 font-medium">health</th>
                    <th className="px-2 py-2 text-right font-medium">docs</th>
                    <th className="px-4 py-2 text-right font-medium">size</th>
                  </tr>
                </thead>
                <tbody>
                  {(snapshot?.indexes ?? []).map((index) => (
                    <tr key={index.index} className="border-t border-white/5">
                      <td className="max-w-[260px] truncate px-4 py-2 text-zinc-300">{index.index}</td>
                      <td className="px-2 py-2">
                        <span className={index.health === "green" ? "text-emerald-400" : index.health === "yellow" ? "text-yellow-400" : "text-red-400"}>
                          {index.health}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-right text-zinc-400">{index.docs_count}</td>
                      <td className="px-4 py-2 text-right text-zinc-500">{index.store_size}</td>
                    </tr>
                  ))}
                  {snapshot && snapshot.indexes.length === 0 && (
                    <tr><td colSpan={4} className="px-4 py-8 text-center text-zinc-600">인덱스 없음</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-md border border-white/10 bg-[#141414]">
            <SectionTitle title="Recent RAG Searches" />
            <div className="divide-y divide-white/5">
              {recentRagEvents.map((event, index) => (
                <div key={`${event.timestamp}-${index}`} className="px-4 py-3 text-xs">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-zinc-300">project {event.project_id ?? "-"}</span>
                    <span className="text-zinc-600">{formatTime(event.timestamp)}</span>
                  </div>
                  <p className="mt-1 text-zinc-500">top_k {event.top_k ?? "-"} / result {event.result_count ?? 0}</p>
                  <p className="mt-1 truncate text-zinc-600">{event.filenames?.join(", ") || "참조 파일 없음"}</p>
                </div>
              ))}
              {recentRagEvents.length === 0 && <p className="px-4 py-8 text-center text-xs text-zinc-600">최근 RAG 이벤트 없음</p>}
            </div>
          </div>

          <div className="rounded-md border border-white/10 bg-[#141414]">
            <SectionTitle title="Recent LLM Calls" />
            <div className="divide-y divide-white/5">
              {recentLlmEvents.map((event, index) => (
                <div key={`${event.timestamp}-${index}`} className="px-4 py-3 text-xs">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-zinc-300">{event.purpose ?? "llm-call"}</span>
                    <span className="text-zinc-600">{formatTime(event.timestamp)}</span>
                  </div>
                  <p className="mt-1 truncate text-zinc-500">{event.model ?? "-"}</p>
                  <p className="mt-1 text-zinc-600">tokens {event.tokens_input ?? 0} / {event.tokens_output ?? 0}, {event.duration_ms ?? "-"} ms</p>
                </div>
              ))}
              {recentLlmEvents.length === 0 && <p className="px-4 py-8 text-center text-xs text-zinc-600">최근 LLM 이벤트 없음</p>}
            </div>
          </div>
        </section>

        <section className="rounded-md border border-white/10 bg-[#141414]">
          <SectionTitle
            title="Recent Elasticsearch Events"
            right={<span className="text-xs text-zinc-600">{snapshot?.recent_events.length ?? 0}개</span>}
          />
          <div className="max-h-80 overflow-y-auto">
            {(snapshot?.recent_events ?? []).map((event, index) => (
              <div key={`${event.timestamp}-${index}`} className="grid gap-2 border-t border-white/5 px-4 py-3 text-xs md:grid-cols-[130px_120px_1fr_100px]">
                <span className="text-zinc-600">{formatTime(event.timestamp)}</span>
                <span className={`w-fit rounded border px-2 py-0.5 ${EVENT_BADGE[event.event_type] ?? "border-white/10 bg-white/5 text-zinc-300"}`}>{event.event_type}</span>
                <span className="truncate text-zinc-300">
                  {event.method ? `${event.method} ` : ""}{event.path ?? event.route ?? event.purpose ?? "-"}
                </span>
                <span className="text-right text-zinc-500">{event.duration_ms ? `${event.duration_ms} ms` : event.status_code ?? ""}</span>
              </div>
            ))}
            {snapshot && snapshot.recent_events.length === 0 && (
              <p className="px-4 py-8 text-center text-xs text-zinc-600">최근 Elasticsearch 이벤트 없음</p>
            )}
          </div>
        </section>

        <section className="rounded-md border border-white/10 bg-[#101010] font-mono">
          <SectionTitle
            title="Live Logs"
            right={<span className="text-xs text-zinc-600">{filtered.length} / {logs.length} 항목</span>}
          />
          <div className="flex flex-wrap items-center gap-4 border-b border-white/10 px-4 py-2">
            <div className="flex items-center gap-1.5">
              <span className="text-zinc-600 text-xs mr-1">레벨</span>
              {ALL_LEVELS.map((level) => (
                <button key={level} onClick={() => toggleLevel(level)}
                  className={`text-xs px-2 py-0.5 rounded transition-colors ${filterLevel.includes(level) ? (LEVEL_BADGE[level] ?? "bg-zinc-700 text-zinc-300") : "bg-transparent text-zinc-600 border border-zinc-700"}`}>
                  {level}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-zinc-600 text-xs mr-1">소스</span>
              {ALL_SOURCES.map((source) => (
                <button key={source} onClick={() => toggleSource(source)}
                  className={`text-xs px-2 py-0.5 rounded transition-colors ${filterSource.includes(source) ? (SOURCE_BADGE[source] ?? "bg-zinc-700 text-zinc-300") : "bg-transparent text-zinc-600 border border-zinc-700"}`}>
                  {source}
                </button>
              ))}
            </div>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="메시지 검색..."
              className="w-48 rounded border border-zinc-700 bg-transparent px-2 py-0.5 text-xs text-zinc-300 outline-none placeholder-zinc-600 focus:border-zinc-500"
            />
            <button onClick={() => setAutoScroll(true)}
              className={`ml-auto rounded px-2 py-1 text-xs transition-colors ${autoScroll ? "bg-emerald-800 text-emerald-300" : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"}`}>
              자동 스크롤
            </button>
            <button onClick={handleClear}
              className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-400 transition-colors hover:bg-red-900/50 hover:text-red-300">
              초기화
            </button>
          </div>
          <div ref={containerRef} onScroll={handleScroll} className="max-h-96 overflow-y-auto px-2 py-2">
            {filtered.length === 0 ? (
              <div className="flex h-40 items-center justify-center text-sm text-zinc-600">
                {logs.length === 0 ? "로그 대기 중..." : "필터 조건에 맞는 로그 없음"}
              </div>
            ) : (
              filtered.map((log, index) => (
                <div key={index} className={`flex items-start gap-2 rounded px-3 py-1 hover:bg-white/5 ${LEVEL_STYLE[log.level] ?? "text-zinc-300"}`}>
                  <span className="w-[88px] flex-shrink-0 pt-px text-xs text-zinc-600">{log.ts}</span>
                  <span className={`w-[60px] flex-shrink-0 rounded px-1.5 py-px text-center text-xs ${LEVEL_BADGE[log.level] ?? "bg-zinc-700 text-zinc-300"}`}>
                    {log.level}
                  </span>
                  <span className={`w-[64px] flex-shrink-0 rounded px-1.5 py-px text-center text-xs ${SOURCE_BADGE[log.source] ?? "bg-zinc-700 text-zinc-400"}`}>
                    {log.source}
                  </span>
                  <span className="flex-1 break-all text-xs leading-relaxed">{log.msg}</span>
                </div>
              ))
            )}
            <div ref={bottomRef} />
          </div>
        </section>
      </main>
    </div>
  );
}
