"use client";

import { useState } from "react";
import Link from "next/link";

import type { ConvSummary } from "@/lib/api";
import { ROUTES } from "@/lib/routes";
import type { ProjectInfo } from "./types";

type SidebarProps = {
  isLoggedIn: boolean;
  conversations: ConvSummary[];
  projects: ProjectInfo[];
  activeConvId: number | null;
  activeProjectId: number | null;
  onNew: () => void;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
  onSelectProject: (project: ProjectInfo) => void;
  onSaveConversationNote: (convId: number, note: string | null) => void;
  onLogin: () => void;
  onLogout: () => void;
  onSettings: () => void;
};

export function Sidebar({
  isLoggedIn,
  conversations,
  projects,
  activeConvId,
  activeProjectId,
  onNew,
  onSelect,
  onDelete,
  onSelectProject,
  onSaveConversationNote,
  onLogin,
  onLogout,
  onSettings,
}: SidebarProps) {
  const [editingNoteId, setEditingNoteId] = useState<number | null>(null);
  const [noteDraft, setNoteDraft] = useState("");

  function openNoteEditor(conv: ConvSummary) {
    setEditingNoteId(conv.id);
    setNoteDraft(conv.note ?? "");
  }

  function saveNote(convId: number) {
    const note = noteDraft.trim();
    onSaveConversationNote(convId, note.length > 0 ? note : null);
    setEditingNoteId(null);
  }

  return (
    <aside className="w-64 flex-shrink-0 bg-[#171717] flex flex-col h-full">
      <div className="px-4 pt-5 pb-3 flex items-center gap-2">
        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
        </svg>
        <span className="text-white font-semibold text-sm">AI Code Review</span>
      </div>

      <div className="px-3 mb-1">
        <button onClick={onNew} className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-zinc-300 hover:bg-white/10 transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          새 대화
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 space-y-0.5">
        {isLoggedIn ? (
          <>
            {projects.length > 0 && (
              <div className="pt-3">
                <p className="text-xs text-zinc-500 px-3 pb-1 font-medium">프로젝트</p>
                {projects.map((project) => (
                  <button
                    key={project.id}
                    onClick={() => onSelectProject(project)}
                    className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${project.id === activeProjectId ? "bg-indigo-500/15" : "hover:bg-white/5"}`}
                    title={project.name}
                  >
                    <span className={project.id === activeProjectId ? "block text-sm text-indigo-200 truncate" : "block text-sm text-zinc-400 truncate"}>
                      {project.name}
                    </span>
                    <span className="block text-xs text-zinc-600 mt-0.5">
                      {project.file_count}개 파일 / {project.chunk_count}개 청크
                    </span>
                  </button>
                ))}
              </div>
            )}

            {conversations.length > 0 && (
              <p className="text-xs text-zinc-500 px-3 pt-3 pb-1 font-medium">대화 내역</p>
            )}
            {conversations.map((c) => (
              <div key={c.id}>
                <div
                  className={`group flex items-center rounded-lg transition-colors ${c.id === activeConvId ? "bg-white/10" : "hover:bg-white/5"}`}
                >
                  <button onClick={() => onSelect(c.id)}
                    className="flex-1 text-left px-3 py-2 text-sm truncate min-w-0"
                    title={c.title}>
                    <span className={c.id === activeConvId ? "text-white" : "text-zinc-400 group-hover:text-zinc-200"}>
                      {c.title || "새 대화"}
                    </span>
                    <span className="block text-xs text-zinc-600 mt-0.5">
                      {c.message_count}개 메시지
                    </span>
                    {c.note && <span className="block text-xs text-zinc-500 mt-0.5 truncate">{c.note}</span>}
                  </button>
                  {c.id === activeConvId && (
                    <button onClick={() => openNoteEditor(c)}
                      className="flex-shrink-0 px-2 py-2 text-zinc-600 hover:text-zinc-300 opacity-0 group-hover:opacity-100 transition-all"
                      title="대화 메모">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h8M8 11h8m-8 4h5M5 5a2 2 0 012-2h10a2 2 0 012 2v14l-4-2H7a2 2 0 01-2-2V5z" />
                      </svg>
                    </button>
                  )}
                  <button onClick={(e) => { e.stopPropagation(); onDelete(c.id); }}
                    className="flex-shrink-0 px-2 py-2 text-zinc-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                    title="대화 삭제">
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
                {editingNoteId === c.id && (
                  <div className="mx-1 mt-1 mb-2 rounded-lg border border-white/10 bg-white/[0.03] p-2">
                    <textarea
                      value={noteDraft}
                      onChange={(e) => setNoteDraft(e.target.value)}
                      rows={3}
                      className="w-full resize-none rounded-md border border-white/10 bg-[#111] px-2 py-1 text-xs text-zinc-300 outline-none focus:border-white/30"
                      placeholder="대화에 남길 메모"
                    />
                    <div className="mt-2 flex justify-end gap-2">
                      <button onClick={() => setEditingNoteId(null)} className="text-xs text-zinc-500 hover:text-zinc-300">취소</button>
                      <button onClick={() => saveNote(c.id)} className="text-xs text-zinc-300 hover:text-white">저장</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </>
        ) : (
          <div className="px-3 pt-6 text-center">
            <p className="text-zinc-500 text-xs leading-relaxed">
              대화 내역을 저장하려면 로그인하세요.
            </p>
            <button onClick={onLogin}
              className="mt-3 w-full text-sm bg-white/10 hover:bg-white/20 text-white rounded-lg py-2 transition-colors">
              로그인
            </button>
          </div>
        )}
      </div>

      <div className="px-3 py-4 border-t border-white/10 space-y-1">
        <div className="flex items-center gap-1">
          <button onClick={onSettings}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-zinc-500 hover:bg-white/10 hover:text-zinc-300 transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
            </svg>
            설정
          </button>
          <Link href={ROUTES.ADMIN}
            className="flex-1 flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-zinc-500 hover:bg-white/10 hover:text-zinc-300 transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            로그 뷰어
          </Link>
        </div>
        {isLoggedIn ? (
          <button onClick={onLogout} className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-zinc-400 hover:bg-white/10 hover:text-white transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            로그아웃
          </button>
        ) : null}
      </div>
    </aside>
  );
}
