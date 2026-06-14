"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { Message } from "./types";

type MessageBubbleProps = {
  msg: Message;
  onRegenerate?: (msg: Message) => void;
  onDelete?: (msg: Message) => void;
  onSaveNote?: (msg: Message, note: string | null) => void;
};

function canUseStoredActions(msg: Message) {
  return /^\d+$/.test(msg.id);
}

function MessageNoteEditor({
  initialNote,
  placeholder,
  onCancel,
  onSave,
}: {
  initialNote: string;
  placeholder: string;
  onCancel: () => void;
  onSave: (note: string | null) => void;
}) {
  const [draft, setDraft] = useState(initialNote);

  function save() {
    const trimmed = draft.trim();
    onSave(trimmed.length > 0 ? trimmed : null);
  }

  return (
    <div className="mt-2 max-w-md space-y-2">
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={2}
        className="w-full resize-none rounded-lg border border-white/10 bg-[#1f1f1f] px-2 py-1.5 text-xs text-zinc-200 outline-none focus:border-white/30"
        placeholder={placeholder}
      />
      <div className="flex justify-end gap-2">
        <button onClick={onCancel} className="text-xs text-zinc-500 hover:text-zinc-300">취소</button>
        <button onClick={save} className="text-xs text-zinc-300 hover:text-white">저장</button>
      </div>
    </div>
  );
}

export function MessageBubble({ msg, onRegenerate, onDelete, onSaveNote }: MessageBubbleProps) {
  const [noteOpen, setNoteOpen] = useState(false);
  const stored = canUseStoredActions(msg);

  if (msg.role === "user") {
    return (
      <div className="flex justify-end px-4 py-2">
        <div className="max-w-[75%] bg-[#2f2f2f] text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm">
          {msg.filename && (
            <div className="flex items-center gap-1.5 mb-1.5 text-zinc-400 text-xs">
              <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              {msg.filename}
            </div>
          )}
          <span className="whitespace-pre-wrap">{msg.content}</span>
          {msg.note && (
            <p className="mt-2 border-t border-white/10 pt-2 text-xs text-zinc-400 whitespace-pre-wrap">{msg.note}</p>
          )}
          {stored && onSaveNote && (
            <div className="mt-2 flex justify-end">
              <button onClick={() => setNoteOpen((v) => !v)} className="text-xs text-zinc-500 hover:text-zinc-300">
                메모
              </button>
            </div>
          )}
          {noteOpen && onSaveNote && (
            <MessageNoteEditor
              initialNote={msg.note ?? ""}
              placeholder="이 메시지에 남길 메모"
              onCancel={() => setNoteOpen(false)}
              onSave={(note) => {
                onSaveNote(msg, note);
                setNoteOpen(false);
              }}
            />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 px-4 py-3">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-white/10 flex items-center justify-center mt-0.5">
        <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
        </svg>
      </div>
      <div className="flex-1 min-w-0 pt-1">
        {msg.ragRefs && msg.ragRefs.length > 0 && (
          <details className="mb-3 group/rag">
            <summary className="cursor-pointer flex items-center gap-1.5 text-xs text-indigo-400/80 hover:text-indigo-300 select-none list-none">
              <svg className="w-3.5 h-3.5 transition-transform group-open/rag:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
              참조 코드 {msg.ragRefs.length}개
            </summary>
            <div className="mt-2 ml-1 pl-3 border-l-2 border-indigo-900/50 space-y-1.5">
              {msg.ragRefs.map((r, i) => (
                <div key={i} className="flex items-baseline gap-2 text-xs">
                  <span className="text-indigo-400/60 font-mono">{r.chunk_type}</span>
                  <span className="text-indigo-300 font-mono font-medium">{r.name}</span>
                  <span className="text-zinc-600">{r.filename}</span>
                  <span className="text-zinc-700">L{r.start_line}-{r.end_line}</span>
                </div>
              ))}
            </div>
          </details>
        )}

        {msg.webRefs && msg.webRefs.length > 0 && (
          <details className="mb-3 group/web">
            <summary className="cursor-pointer flex items-center gap-1.5 text-xs text-emerald-400/80 hover:text-emerald-300 select-none list-none">
              <svg className="w-3.5 h-3.5 transition-transform group-open/web:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9" />
              </svg>
              웹 검색 결과 {msg.webRefs.length}개
            </summary>
            <div className="mt-2 ml-1 pl-3 border-l-2 border-emerald-900/50 space-y-2">
              {msg.webRefs.map((r, i) => (
                <div key={i} className="text-xs">
                  <a href={r.url} target="_blank" rel="noopener noreferrer"
                    className="text-emerald-400 hover:text-emerald-300 hover:underline font-medium">
                    {i + 1}. {r.title}
                  </a>
                  <p className="text-zinc-600 mt-0.5 leading-relaxed line-clamp-2">{r.snippet}</p>
                </div>
              ))}
            </div>
          </details>
        )}

        {msg.thinkContent && (
          <details open={!msg.thinkDone} className="mb-3 group/think">
            <summary className="cursor-pointer flex items-center gap-1.5 text-xs text-purple-400/80 hover:text-purple-300 select-none list-none">
              <svg className="w-3.5 h-3.5 transition-transform group-open/think:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              <span className="flex items-center gap-1">
                {!msg.thinkDone && (
                  <span className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-pulse" />
                )}
                {msg.thinkDone ? "생각 과정 보기" : "생각 중..."}
              </span>
            </summary>
            <div className="mt-2 ml-1 pl-3 border-l-2 border-purple-900/50 text-zinc-500 text-xs whitespace-pre-wrap leading-relaxed max-h-52 overflow-y-auto font-mono">
              {msg.thinkContent.replace(/<\/?think>/g, "").trim()}
            </div>
          </details>
        )}

        {msg.loading && !msg.thinkContent ? (
          <div className="flex items-center gap-2 text-zinc-400 text-sm">
            <span className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce [animation-delay:0ms]" />
            <span className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce [animation-delay:150ms]" />
            <span className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce [animation-delay:300ms]" />
            <span className="ml-1">{msg.statusMsg || (msg.reviewStatus === "processing" ? "로컬 LLM 분석 중..." : "생각 중...")}</span>
          </div>
        ) : msg.content ? (
          <>
            <div className="prose prose-sm prose-invert max-w-none text-zinc-100 [&_code]:bg-white/10 [&_code]:px-1 [&_code]:rounded [&_pre]:bg-[#1a1a1a] [&_pre]:border [&_pre]:border-white/10">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
            </div>
            {msg.isRegenerated && <p className="mt-2 text-xs text-zinc-600">재생성된 응답</p>}
            {msg.note && (
              <p className="mt-3 border-l border-white/10 pl-3 text-xs text-zinc-500 whitespace-pre-wrap">{msg.note}</p>
            )}
            {stored && (
              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-zinc-600">
                {onRegenerate && <button onClick={() => onRegenerate(msg)} className="hover:text-zinc-300">재생성</button>}
                {onSaveNote && <button onClick={() => setNoteOpen((v) => !v)} className="hover:text-zinc-300">메모</button>}
                {onDelete && <button onClick={() => onDelete(msg)} className="hover:text-red-300">삭제</button>}
              </div>
            )}
            {noteOpen && onSaveNote && (
              <MessageNoteEditor
                initialNote={msg.note ?? ""}
                placeholder="이 응답에 남길 메모"
                onCancel={() => setNoteOpen(false)}
                onSave={(note) => {
                  onSaveNote(msg, note);
                  setNoteOpen(false);
                }}
              />
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}
