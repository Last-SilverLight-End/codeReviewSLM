import { useEffect, useRef, useState } from "react";

import { CODE_FILE_EXTS, IMAGE_EXTS } from "./types";
/* ── 파일 관련 상수 ── */

function isImageFile(f: File) {
  const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
  return IMAGE_EXTS.includes(ext) || f.type.startsWith("image/");
}

export function ChatInput({
  onSend, onZipUpload, disabled, projectMode, thinkMode, onThinkModeToggle, webSearch, onWebSearchToggle,
}: {
  onSend: (text: string, file?: File, imageFile?: File) => void;
  onZipUpload: (file: File) => void;
  disabled: boolean;
  projectMode: boolean;
  thinkMode: boolean;
  onThinkModeToggle: () => void;
  webSearch: boolean;
  onWebSearchToggle: () => void;
}) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const zipRef = useRef<HTMLInputElement>(null);
  const imageRef = useRef<HTMLInputElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);

  function selectImage(f: File) {
    setImageFile(f);
    const reader = new FileReader();
    reader.onload = (e) => setImagePreview(e.target?.result as string);
    reader.readAsDataURL(f);
  }

  function removeImage() {
    setImageFile(null);
    setImagePreview(null);
    if (imageRef.current) imageRef.current.value = "";
  }

  function send() {
    if (disabled || (!text.trim() && !file && !imageFile)) return;
    onSend(text.trim(), file ?? undefined, imageFile ?? undefined);
    setText("");
    setFile(null);
    removeImage();
    if (fileRef.current) fileRef.current.value = "";
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  }

  useEffect(() => {
    const ta = textRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  }, [text]);

  const placeholder = projectMode && imageFile
    ? "이미지 + 프로젝트 분석: 에러 화면, 스크린샷에 대해 질문하세요..."
    : projectMode
      ? "프로젝트 코드에 대해 질문하세요... (Hybrid RAG 검색)"
      : imageFile
        ? "이미지에 대해 질문하세요..."
        : file
          ? "파일에 대해 질문하거나 그냥 전송하세요..."
          : "코드를 붙여넣거나 질문하세요... (Shift+Enter 줄바꿈)";

  return (
    <div className="px-4 pb-4">
      <div onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault(); setDragging(false);
          const f = e.dataTransfer.files[0];
          if (!f) return;
          if (f.name.endsWith(".zip")) { onZipUpload(f); }
          else if (isImageFile(f)) { selectImage(f); }
          else { setFile(f); }
        }}
        className={`bg-[#2f2f2f] rounded-2xl border transition-colors ${dragging ? "border-indigo-400/60" : "border-white/10"}`}>

        {/* 이미지 미리보기 */}
        {imagePreview && (
          <div className="flex items-start gap-2 px-4 pt-3 pb-1">
            <div className="relative">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imagePreview} alt="preview" className="h-20 rounded-lg object-cover border border-white/10" />
              <button onClick={removeImage}
                className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-zinc-700 hover:bg-zinc-600 rounded-full flex items-center justify-center text-zinc-300">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <span className="text-xs text-zinc-500 mt-1">{imageFile?.name}</span>
          </div>
        )}

        {/* 코드 파일 첨부 표시 */}
        {file && (
          <div className="flex items-center gap-2 px-4 pt-3 pb-1">
            <div className="flex items-center gap-2 bg-white/10 rounded-lg px-3 py-1.5 text-sm text-zinc-300">
              <svg className="w-4 h-4 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span>{file.name}</span>
              <span className="text-zinc-500 text-xs">({(file.size / 1024).toFixed(1)} KB)</span>
            </div>
            <button onClick={() => setFile(null)} className="text-zinc-500 hover:text-white">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        <div className="flex items-end gap-2 px-4 py-3">
          {/* 이미지 업로드 */}
          <input ref={imageRef} type="file" accept="image/*" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) selectImage(f); }} />
          <button type="button" onClick={() => imageRef.current?.click()} disabled={disabled}
            title={projectMode ? "이미지 첨부 (프로젝트 코드와 함께 분석)" : "이미지 첨부 (jpg, png, webp 등)"}

            className={`flex-shrink-0 transition-colors disabled:opacity-40 mb-0.5 ${imageFile ? "text-emerald-400 hover:text-emerald-300" : "text-zinc-400 hover:text-white"}`}>
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </button>

          {/* 단일 파일 업로드 */}
          <input ref={fileRef} type="file" accept={CODE_FILE_EXTS} className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) setFile(f); }} />
          <button type="button" onClick={() => fileRef.current?.click()} disabled={disabled || projectMode}
            title="소스 파일 첨부 (.py .js .ts .java .html)"
            className="flex-shrink-0 text-zinc-400 hover:text-white transition-colors disabled:opacity-40 mb-0.5">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
            </svg>
          </button>

          {/* 프로젝트 zip 업로드 */}
          <input ref={zipRef} type="file" accept=".zip" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) { onZipUpload(f); if (zipRef.current) zipRef.current.value = ""; } }} />
          <button type="button" onClick={() => zipRef.current?.click()} disabled={disabled}
            title="프로젝트 폴더 업로드 (.zip)"
            className={`flex-shrink-0 transition-colors disabled:opacity-40 mb-0.5 ${projectMode ? "text-indigo-400 hover:text-indigo-300" : "text-zinc-400 hover:text-white"}`}>
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
          </button>

          <textarea ref={textRef} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={handleKey}
            placeholder={placeholder}
            rows={1} disabled={disabled}
            className="flex-1 bg-transparent text-white placeholder-zinc-500 text-sm resize-none outline-none leading-relaxed disabled:opacity-50"
            style={{ maxHeight: "160px" }} />

          {/* 웹 검색 토글 */}
          <button type="button" onClick={onWebSearchToggle} disabled={disabled}
            title={webSearch ? "웹 검색 ON: DuckDuckGo 검색 후 답변 (클릭하여 끄기)" : "웹 검색 OFF: 클릭하여 인터넷 검색 활성화"}
            className={`flex-shrink-0 transition-colors disabled:opacity-40 mb-0.5 ${
              webSearch
                ? "text-emerald-400 hover:text-emerald-300 drop-shadow-[0_0_6px_rgba(52,211,153,0.6)]"
                : "text-zinc-500 hover:text-zinc-300"
            }`}>
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9" />
            </svg>
          </button>

          {/* Think 모드 토글 */}
          <button type="button" onClick={onThinkModeToggle} disabled={disabled}
            title={thinkMode ? "Think 모드 ON: 생각 과정을 보여줍니다 (클릭하여 끄기)" : "Think 모드 OFF: 클릭하여 생각 과정 표시"}
            className={`flex-shrink-0 transition-colors disabled:opacity-40 mb-0.5 ${
              thinkMode
                ? "text-purple-400 hover:text-purple-300 drop-shadow-[0_0_6px_rgba(168,85,247,0.6)]"
                : "text-zinc-500 hover:text-zinc-300"
            }`}>
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </button>

          <button type="button" onClick={send} disabled={disabled || (!text.trim() && !file && !imageFile)}
            className="flex-shrink-0 w-8 h-8 rounded-full bg-white flex items-center justify-center hover:bg-zinc-200 transition-colors disabled:opacity-30 disabled:cursor-not-allowed mb-0.5">
            <svg className="w-4 h-4 text-black" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>
      <p className="text-center text-xs text-zinc-600 mt-2">
        {thinkMode && <span className="text-purple-500/80 mr-1">Think</span>}
        {webSearch && <span className="text-emerald-500/80 mr-1">웹 검색</span>}
        {projectMode && imageFile
          ? "멀티모달 RAG: 이미지 분석 결과를 코드베이스 검색과 연결해 답변합니다"
          : projectMode
          ? "프로젝트 모드: pgvector와 Elasticsearch를 함께 검색해 답변합니다"
          : "파일 첨부: 코드 리뷰 / zip 첨부: 프로젝트 분석 / 텍스트: 코드 질문"}
      </p>
    </div>
  );
}

