"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { api, clearAllTokens, getToken, streamConvMessage, type ChatMsg, type ConvSummary, type MsgResp } from "@/lib/api";
import { SSE } from "@/lib/sse-events";
import { ROUTES } from "@/lib/routes";
import { ChatInput } from "@/components/chat/chat-input";
import { EmptyState } from "@/components/chat/empty-state";
import { MessageBubble } from "@/components/chat/message-bubble";
import { ProjectBanner } from "@/components/chat/project-banner";
import { SettingsPanel } from "@/components/chat/settings-panel";
import { Sidebar } from "@/components/chat/sidebar";
import { DEFAULT_SETTINGS, REVIEW_POLL_INTERVAL_MS, toModelOptions, uid, type AppSettings, type Message, type ProjectInfo, type RagRef, type WebRef } from "@/components/chat/types";

const ACTIVE_CONVERSATION_KEY = "chat_active_conversation_id";
const ACTIVE_PROJECT_KEY = "chat_active_project_id";
/* ── API 메시지 → 로컬 메시지 변환 ── */
function toLocalMsg(m: MsgResp): Message {
  return {
    id: String(m.id),
    role: m.role as "user" | "assistant",
    content: m.content,
    note: m.note,
    isRegenerated: m.is_regenerated,
    deletedAt: m.deleted_at,
  };
}

/* ── SSE 스트림 읽기 헬퍼 ── */
async function readStream(
  response: Response,
  onToken: (token: string) => void,
  onDone: (data?: Record<string, unknown>) => void,
  onError: (msg: string) => void,
  onStatus?: (msg: string) => void,
  onThink?: (token: string) => void,
  onRagRefs?: (refs: RagRef[]) => void,
  onWebRefs?: (refs: WebRef[]) => void,
) {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        // keep-alive comment 무시 (": ping")
        if (line.startsWith(":")) continue;
        if (!line.startsWith("data: ")) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data[SSE.STATUS] && onStatus) onStatus(data[SSE.STATUS]);
          if (data[SSE.THINK] && onThink) onThink(data[SSE.THINK]);
          if (data[SSE.RAG_REFS] && onRagRefs) onRagRefs(data[SSE.RAG_REFS]);
          if (data[SSE.WEB_REFS] && onWebRefs) onWebRefs(data[SSE.WEB_REFS]);
          if (data[SSE.TOKEN]) onToken(data[SSE.TOKEN]);
          if (data[SSE.DONE]) { finished = true; onDone(data); }
          if (data[SSE.ERROR]) { onError(data[SSE.ERROR]); return; }
        } catch { /* JSON 파싱 실패 시 skip */ }
      }
    }
    // 서버가 done 이벤트 없이 스트림을 닫은 경우
    if (!finished) onDone();
  } finally {
    reader.releaseLock();
  }
}

/* ── 메인 페이지 ── */
export default function MainPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversations, setConversations] = useState<ConvSummary[]>([]);
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [activeReviewId, setActiveReviewId] = useState<number | null>(null);
  const [activeProject, setActiveProject] = useState<ProjectInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [thinkMode, setThinkMode] = useState(false);
  const [webSearch, setWebSearch] = useState(false);
  const [appSettings, setAppSettings] = useState<AppSettings>(() => {
    if (typeof window === "undefined") return DEFAULT_SETTINGS;
    try {
      const saved = localStorage.getItem("app_settings");
      return saved ? { ...DEFAULT_SETTINGS, ...JSON.parse(saved) } : DEFAULT_SETTINGS;
    } catch {
      return DEFAULT_SETTINGS;
    }
  });
  const [showSettings, setShowSettings] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const activeStreamAbortRef = useRef<AbortController | null>(null);

  const clearActiveStream = useCallback(() => {
    activeStreamAbortRef.current?.abort();
    activeStreamAbortRef.current = null;
  }, []);

  useEffect(() => clearActiveStream, [clearActiveStream]);

  useEffect(() => {
    const timer = window.setTimeout(() => setIsLoggedIn(!!getToken()), 0);
    return () => window.clearTimeout(timer);
  }, []);

  // 설정 변경 시 localStorage에 저장
  useEffect(() => {
    try { localStorage.setItem("app_settings", JSON.stringify(appSettings)); } catch { /* 무시 */ }
  }, [appSettings]);

  const persistActiveConversation = useCallback((convId: number | null) => {
    setActiveConvId(convId);
    try {
      if (convId === null) localStorage.removeItem(ACTIVE_CONVERSATION_KEY);
      else localStorage.setItem(ACTIVE_CONVERSATION_KEY, String(convId));
    } catch { /* ignore */ }
  }, []);

  const persistActiveProject = useCallback((project: ProjectInfo | null) => {
    setActiveProject(project);
    try {
      if (project === null) localStorage.removeItem(ACTIVE_PROJECT_KEY);
      else localStorage.setItem(ACTIVE_PROJECT_KEY, String(project.id));
    } catch { /* ignore */ }
  }, []);

  const loadConversations = useCallback(async () => {
    if (!getToken()) return [];
    try {
      const list = await api.listConversations();
      setConversations(list);
      return list;
    } catch { /* 토큰 만료 등 */ }
    return [];
  }, []);

  const loadProjects = useCallback(async () => {
    if (!getToken()) return [];
    try {
      const list = await api.listProjects();
      setProjects(list);
      return list;
    } catch {
      return [];
    }
  }, []);

  const restoreConversation = useCallback(async (convId: number, projectList: ProjectInfo[]) => {
    try {
      const detail = await api.getConversation(convId);
      let conversationProject: ProjectInfo | null = null;
      if (detail.project_id !== null) {
        conversationProject = projectList.find((project) => project.id === detail.project_id) ?? null;
      }
      persistActiveConversation(convId);
      persistActiveProject(conversationProject);
      setActiveReviewId(null);
      setMessages(detail.messages.map(toLocalMsg));
    } catch {
      persistActiveConversation(null);
    }
  }, [persistActiveConversation, persistActiveProject]);

  useEffect(() => {
    void Promise.resolve().then(async () => {
      const [conversationList, projectList] = await Promise.all([loadConversations(), loadProjects()]);
      const savedConvId = Number(localStorage.getItem(ACTIVE_CONVERSATION_KEY));
      if (Number.isInteger(savedConvId) && savedConvId > 0) {
        await restoreConversation(savedConvId, projectList);
        return;
      }
      const savedProjectId = Number(localStorage.getItem(ACTIVE_PROJECT_KEY));
      if (Number.isInteger(savedProjectId) && savedProjectId > 0) {
        const project = projectList.find((item) => item.id === savedProjectId) ?? null;
        if (project) persistActiveProject(project);
      }
      if (conversationList.length === 0) persistActiveConversation(null);
    });
  }, [loadConversations, loadProjects, persistActiveConversation, persistActiveProject, restoreConversation]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // 단일 파일 리뷰 폴링
  useEffect(() => {
    if (!activeReviewId) return;
    const last = messages.findLast((m) => m.role === "assistant");
    // reviewStatus가 없는 메시지(텍스트 채팅)는 폴링 대상 아님
    if (!last?.loading || !last.reviewStatus) return;

    const iv = setInterval(async () => {
      try {
        const r = await api.getReview(activeReviewId);
        if (r.status === "completed" || r.status === "failed") {
          setMessages((prev) => prev.map((m) =>
            m.id === last.id
              ? { ...m, loading: false, content: r.status === "completed" ? (r.result ?? "") : `리뷰 실패: ${r.error}`, reviewStatus: r.status }
              : m
          ));
          setBusy(false);
          setActiveReviewId(null);  // 완료 후 초기화
          loadConversations();
        } else {
          setMessages((prev) => prev.map((m) => m.id === last.id ? { ...m, reviewStatus: r.status } : m));
        }
      } catch { /* 무시 */ }
    }, REVIEW_POLL_INTERVAL_MS);
    return () => clearInterval(iv);
  }, [activeReviewId, messages, loadConversations]);

  function addMsg(msg: Message) { setMessages((p) => [...p, msg]); }

  async function handleZipUpload(file: File) {
    if (!getToken()) {
      addMsg({ id: uid(), role: "assistant", content: `프로젝트 업로드는 로그인이 필요합니다.\n\n[로그인하기](${ROUTES.LOGIN}) 후 다시 시도해주세요.`, loading: false });
      return;
    }
    setBusy(true);
    const botId = uid();
    addMsg({ id: uid(), role: "user", content: `${file.name} 업로드 중...`, filename: file.name });
    addMsg({ id: botId, role: "assistant", content: "", loading: true, reviewStatus: "pending" });

    try {
      const result = await api.uploadProject(file);
      const project = { id: result.project_id, name: result.name, file_count: result.file_count, chunk_count: result.chunk_count };
      persistActiveProject(project);
      setProjects((prev) => [project, ...prev.filter((p) => p.id !== project.id)]);
      setMessages((prev) => prev.map((m) => m.id === botId
        ? {
          ...m, loading: false,
          content: `**프로젝트 분석 완료!**\n\n- 파일: ${result.file_count}개\n- 코드 청크: ${result.chunk_count}개\n\n이제 프로젝트 코드에 대해 무엇이든 질문해보세요.`,
        }
        : m
      ));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "업로드 실패";
      setMessages((prev) => prev.map((m) => m.id === botId ? { ...m, loading: false, content: `프로젝트 업로드 실패: ${msg}` } : m));
    } finally {
      setBusy(false);
    }
  }

  async function handleSend(text: string, file?: File, imageFile?: File) {
    setBusy(true);
    const userContent = text || (imageFile ? `이미지를 분석해줘.` : file ? `${file.name} 코드를 리뷰해줘.` : "");
    addMsg({ id: uid(), role: "user", content: userContent, filename: file?.name ?? imageFile?.name });
    const botId = uid();
    addMsg({ id: botId, role: "assistant", content: "", loading: true, reviewStatus: file ? "pending" : undefined });

    try {
      if (imageFile) {
        // 이미지 → vision 모델 (llava:7b) 스위칭
        if (!getToken()) {
          setMessages((prev) => prev.map((m) => m.id === botId
            ? { ...m, loading: false, content: "이미지 분석은 로그인이 필요합니다." }
            : m));
          setBusy(false);
          return;
        }

        // FileReader로 base64 변환 (data:image/...;base64, 접두사 제거)
        const imageB64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = (e) => {
            const result = e.target?.result as string;
            resolve(result.split(",")[1]); // base64 부분만
          };
          reader.onerror = reject;
          reader.readAsDataURL(imageFile);
        });

        let convId = activeConvId;
        let newlyCreatedConvId: number | null = null;
        if (!convId) {
          const conv = await api.createConversation(activeProject?.id);
          convId = conv.id;
          newlyCreatedConvId = conv.id;
          persistActiveConversation(convId);
          setConversations((prev) => [{ ...conv, title: text || imageFile.name }, ...prev]);
        }

        let imgErr: unknown = null;
        try {
          clearActiveStream();
          const abortController = new AbortController();
          activeStreamAbortRef.current = abortController;
          const resp = await streamConvMessage(
            convId, text || "이 이미지를 분석해주세요.",
            undefined, imageB64, activeProject?.id, thinkMode, webSearch,
            toModelOptions(appSettings), appSettings.rag_top_k, appSettings.web_max_results, abortController.signal,
          );
          await readStream(
            resp,
            (token) => setMessages((prev) => prev.map((m) =>
              m.id === botId ? { ...m, loading: false, content: (m.content ?? "") + token } : m
            )),
            (data) => {
              const messageId = typeof data?.message_id === "number" ? String(data.message_id) : null;
              if (messageId) setMessages((prev) => prev.map((m) => m.id === botId ? { ...m, id: messageId } : m));
              setBusy(false);
              activeStreamAbortRef.current = null;
              loadConversations();
            },
            (errMsg) => { throw new Error(errMsg); },
            (statusMsg) => setMessages((prev) => prev.map((m) =>
              m.id === botId ? { ...m, statusMsg } : m
            )),
            (thinkToken) => setMessages((prev) => prev.map((m) =>
              m.id === botId
                ? { ...m, thinkContent: (m.thinkContent ?? "") + thinkToken, thinkDone: thinkToken.includes("</think>") }
                : m
            )),
            (refs) => setMessages((prev) => prev.map((m) =>
              m.id === botId ? { ...m, ragRefs: refs } : m
            )),
            (refs) => setMessages((prev) => prev.map((m) =>
              m.id === botId ? { ...m, webRefs: refs } : m
            )),
          );
        } catch (e) {
          imgErr = e;
          if (newlyCreatedConvId !== null) persistActiveConversation(newlyCreatedConvId);
          activeStreamAbortRef.current = null;
        }
        if (imgErr) throw imgErr;

      } else if (file) {
        if (!getToken()) {
          // 게스트: quickReview (DB 저장 없음)
          const { result } = await api.quickReview(file);
          setMessages((prev) => prev.map((m) => m.id === botId
            ? { ...m, loading: false, content: result }
            : m));
          setBusy(false);
        } else {
          // 로그인: 파일 내용을 읽어 스트리밍으로 전송
          const fileContent = await file.text();
          const reviewContent = `**파일: ${file.name}**\n\n\`\`\`\n${fileContent}\n\`\`\`\n\n${text || "이 코드를 리뷰해주세요."}`;

          setMessages((prev) => prev.map((m) => m.id === botId ? { ...m, reviewStatus: "processing" } : m));

          let convId = activeConvId;
          let newlyCreatedConvId: number | null = null;
          if (!convId) {
            const conv = await api.createConversation();
            convId = conv.id;
            newlyCreatedConvId = conv.id;
            persistActiveConversation(convId);
            setConversations((prev) => [{ ...conv, title: file.name }, ...prev]);
          }

          let fileErr: unknown = null;
          try {
            clearActiveStream();
            const abortController = new AbortController();
            activeStreamAbortRef.current = abortController;
            const resp = await streamConvMessage(
              convId,
              reviewContent,
              undefined,
              undefined,
              activeProject?.id,
              thinkMode,
              webSearch,
              toModelOptions(appSettings),
              appSettings.rag_top_k,
              appSettings.web_max_results,
              abortController.signal,
            );
            await readStream(
              resp,
              (token) => setMessages((prev) => prev.map((m) =>
                m.id === botId ? { ...m, loading: false, content: (m.content ?? "") + token } : m
              )),
              (data) => {
                const messageId = typeof data?.message_id === "number" ? String(data.message_id) : null;
                if (messageId) setMessages((prev) => prev.map((m) => m.id === botId ? { ...m, id: messageId } : m));
                setBusy(false);
                activeStreamAbortRef.current = null;
                loadConversations();
              },
              (errMsg) => { throw new Error(errMsg); },
              undefined,
              (thinkToken) => setMessages((prev) => prev.map((m) =>
                m.id === botId
                  ? { ...m, thinkContent: (m.thinkContent ?? "") + thinkToken, thinkDone: thinkToken.includes("</think>") }
                  : m
              )),
              undefined,
              (refs) => setMessages((prev) => prev.map((m) =>
                m.id === botId ? { ...m, webRefs: refs } : m
              )),
            );
          } catch (e) {
            fileErr = e;
            if (newlyCreatedConvId !== null) persistActiveConversation(newlyCreatedConvId);
            activeStreamAbortRef.current = null;
          }
          if (fileErr) throw fileErr;
        }
      } else if (getToken()) {
        // 로그인 텍스트 채팅 → 대화 API (히스토리 저장)
        let convId = activeConvId;
        let newlyCreatedConvId: number | null = null;
        if (!convId) {
          const conv = await api.createConversation(activeProject?.id);
          convId = conv.id;
          newlyCreatedConvId = conv.id;
          persistActiveConversation(convId);
          // 대화 생성 즉시 사이드바에 추가 (ChatGPT 방식)
          setConversations((prev) => [{
            ...conv,
            title: text.slice(0, 50) || "새 대화",
          }, ...prev]);
        }
        let sendErr: unknown = null;
        try {
          clearActiveStream();
          const abortController = new AbortController();
          activeStreamAbortRef.current = abortController;
          const resp = await streamConvMessage(convId, text, undefined, undefined, activeProject?.id, thinkMode, webSearch, toModelOptions(appSettings), appSettings.rag_top_k, appSettings.web_max_results, abortController.signal);
          await readStream(
            resp,
            (token) => setMessages((prev) => prev.map((m) =>
              m.id === botId ? { ...m, loading: false, content: (m.content ?? "") + token } : m
            )),
            (data) => {
              const messageId = typeof data?.message_id === "number" ? String(data.message_id) : null;
              if (messageId) setMessages((prev) => prev.map((m) => m.id === botId ? { ...m, id: messageId } : m));
              setBusy(false);
              activeStreamAbortRef.current = null;
              loadConversations();
            },
            (errMsg) => { throw new Error(errMsg); },
            undefined,
            (thinkToken) => setMessages((prev) => prev.map((m) =>
              m.id === botId
                ? { ...m, thinkContent: (m.thinkContent ?? "") + thinkToken, thinkDone: thinkToken.includes("</think>") }
                : m
            )),
            (refs) => setMessages((prev) => prev.map((m) =>
              m.id === botId ? { ...m, ragRefs: refs } : m
            )),
            (refs) => setMessages((prev) => prev.map((m) =>
              m.id === botId ? { ...m, webRefs: refs } : m
            )),
          );
        } catch (e) {
          sendErr = e;
          if (newlyCreatedConvId !== null) persistActiveConversation(newlyCreatedConvId);
          activeStreamAbortRef.current = null;
        }
        if (sendErr) throw sendErr;
      } else {
        // 비로그인 텍스트 채팅 (히스토리 미저장)
        const history: ChatMsg[] = messages
          .filter((m) => !m.loading && m.content)
          .map((m) => ({ role: m.role, content: m.content }));
        history.push({ role: "user", content: text });

        const { reply } = await api.chat(history, toModelOptions(appSettings));
        setMessages((prev) => prev.map((m) => m.id === botId ? { ...m, loading: false, content: reply } : m));
        setBusy(false);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "오류가 발생했습니다.";
      setMessages((prev) => prev.map((m) => m.id === botId ? { ...m, loading: false, content: msg } : m));
      setBusy(false);
    }
  }

  async function handleSelectConversation(convId: number) {
    try {
      const detail = await api.getConversation(convId);
      let conversationProject: ProjectInfo | null = null;
      if (detail.project_id !== null) {
        conversationProject = projects.find((project) => project.id === detail.project_id) ?? null;
        if (!conversationProject) {
          const freshProjects = await loadProjects();
          conversationProject = freshProjects.find((project) => project.id === detail.project_id) ?? null;
        }
      }
      persistActiveConversation(convId);
      persistActiveProject(conversationProject);
      setActiveReviewId(null);
      setMessages(detail.messages.map(toLocalMsg));
    } catch { /* 무시 */ }
  }

  function handleSelectProject(project: ProjectInfo) {
    persistActiveProject(project);
    persistActiveConversation(null);
    setActiveReviewId(null);
    setMessages([]);
  }

  async function handleRegenerateMessage(msg: Message) {
    if (!activeConvId || busy) return;
    const msgId = Number(msg.id);
    if (!Number.isInteger(msgId)) return;
    setBusy(true);
    setMessages((prev) => prev.map((m) =>
      m.id === msg.id ? { ...m, loading: true, content: "", statusMsg: "응답 재생성 중..." } : m
    ));
    try {
      const result = await api.regenerateMessage(activeConvId, msgId, toModelOptions(appSettings));
      const regenerated = toLocalMsg(result.assistant_message);
      setMessages((prev) => prev.map((m) => m.id === msg.id ? regenerated : m));
      loadConversations();
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "재생성 실패";
      setMessages((prev) => prev.map((m) =>
        m.id === msg.id ? { ...m, loading: false, content: errorMessage, statusMsg: undefined } : m
      ));
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteMessage(msg: Message) {
    if (!activeConvId || busy) return;
    const msgId = Number(msg.id);
    if (!Number.isInteger(msgId)) return;
    try {
      await api.deleteMessage(activeConvId, msgId);
      setMessages((prev) => prev.filter((m) => m.id !== msg.id));
      loadConversations();
    } catch { /* ignore */ }
  }

  async function handleSaveMessageNote(msg: Message, note: string | null) {
    if (!activeConvId) return;
    const msgId = Number(msg.id);
    if (!Number.isInteger(msgId)) return;
    try {
      await api.updateMessageNote(activeConvId, msgId, note);
      setMessages((prev) => prev.map((m) => m.id === msg.id ? { ...m, note } : m));
    } catch { /* ignore */ }
  }

  async function handleSaveConversationNote(convId: number, note: string | null) {
    try {
      const updated = await api.updateConversationNote(convId, note);
      setConversations((prev) => prev.map((conv) => conv.id === convId ? updated : conv));
    } catch { /* ignore */ }
  }

  async function handleDeleteConversation(convId: number) {
    try {
      await api.deleteConversation(convId);
      if (activeConvId === convId) handleNewChat();
      loadConversations();
    } catch { /* 무시 */ }
  }

  function handleNewChat() {
    setMessages([]);
    persistActiveConversation(null);
    setActiveReviewId(null);
    persistActiveProject(null);
    setBusy(false);
    clearActiveStream();
  }

  function handleLogout() {
    clearAllTokens();
    setIsLoggedIn(false);
    setConversations([]);
    setProjects([]);
    persistActiveConversation(null);
    persistActiveProject(null);
    clearActiveStream();
  }

  return (
    <div className="flex h-screen bg-[#212121] text-white overflow-hidden">
      <Sidebar
        isLoggedIn={isLoggedIn}
        conversations={conversations}
        projects={projects}
        activeConvId={activeConvId}
        activeProjectId={activeProject?.id ?? null}
        onNew={handleNewChat}
        onSelect={handleSelectConversation}
        onDelete={handleDeleteConversation}
        onSelectProject={handleSelectProject}
        onSaveConversationNote={handleSaveConversationNote}
        onLogin={() => router.push(ROUTES.LOGIN)}
        onLogout={handleLogout}
        onSettings={() => setShowSettings(true)}
      />
      {showSettings && (
        <SettingsPanel
          settings={appSettings}
          onClose={() => setShowSettings(false)}
          onChange={(key, val) => setAppSettings((prev) => ({ ...prev, [key]: val }))}
          onReset={() => setAppSettings(DEFAULT_SETTINGS)}
        />
      )}

      <main className="flex-1 flex flex-col min-w-0">
        {activeProject && (
          <ProjectBanner project={activeProject} onExit={() => setActiveProject(null)} />
        )}

        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <EmptyState onExample={(ex) => handleSend(ex)} />
          ) : (
            <div className="max-w-3xl mx-auto w-full py-6">
              {messages.map((m) => (
                <MessageBubble
                  key={m.id}
                  msg={m}
                  onRegenerate={m.role === "assistant" ? handleRegenerateMessage : undefined}
                  onDelete={handleDeleteMessage}
                  onSaveNote={handleSaveMessageNote}
                />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
        <div className="max-w-3xl mx-auto w-full">
          <ChatInput
            onSend={handleSend}
            onZipUpload={handleZipUpload}
            disabled={busy}
            projectMode={!!activeProject}
            thinkMode={thinkMode}
            onThinkModeToggle={() => setThinkMode((v) => !v)}
            webSearch={webSearch}
            onWebSearchToggle={() => setWebSearch((v) => !v)}
          />
        </div>
      </main>
    </div>
  );
}

