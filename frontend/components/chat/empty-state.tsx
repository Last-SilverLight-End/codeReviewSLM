/* ── 빈 상태 ── */
export function EmptyState({ onExample }: { onExample: (text: string) => void }) {
  const examples = [
    "이 코드의 시간복잡도를 분석해줘",
    "Python과 JavaScript의 비동기 처리 차이를 설명해줘",
    "SQL 인젝션 방어 방법을 코드 예시와 함께 알려줘",
    "폴더(zip)를 업로드하면 프로젝트 전체를 분석할 수 있어요",
  ];
  return (
    <div className="h-full flex flex-col items-center justify-center gap-6 px-6 text-center">
      <div>
        <div className="w-16 h-16 rounded-full bg-white/10 flex items-center justify-center mx-auto mb-4">
          <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
          </svg>
        </div>
        <h1 className="text-2xl font-semibold text-white">AI Code Review</h1>
        <p className="text-zinc-400 text-sm mt-2">코드를 질문하거나 파일/프로젝트를 업로드해 분석받으세요</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-xl">
        {examples.map((ex) => (
          <button key={ex} onClick={() => onExample(ex)}
            className="text-left text-sm bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-white/10 text-zinc-300 rounded-xl px-4 py-3 transition-colors">
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}

