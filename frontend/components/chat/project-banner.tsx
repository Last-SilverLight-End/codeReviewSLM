import type { ProjectInfo } from "./types";
/* ── 프로젝트 모드 배너 ── */
export function ProjectBanner({ project, onExit }: { project: ProjectInfo; onExit: () => void }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 bg-indigo-950/60 border-b border-indigo-500/20 text-sm">
      <div className="flex items-center gap-2 text-indigo-300 flex-1 min-w-0">
        <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
        </svg>
        <span className="font-medium truncate">{project.name}</span>
        <span className="text-indigo-500 text-xs flex-shrink-0">
          {project.file_count}개 파일 · {project.chunk_count}개 청크
        </span>
      </div>
      <button onClick={onExit} className="text-indigo-400 hover:text-white transition-colors text-xs flex-shrink-0">
        프로젝트 종료
      </button>
    </div>
  );
}

