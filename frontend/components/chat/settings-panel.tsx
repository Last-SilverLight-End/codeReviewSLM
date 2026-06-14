import type { AppSettings } from "./types";
/* ── 슬라이더 헬퍼 ── */
function Slider({ label, value, min, max, step = 0.01, onChange, description }: {
  label: string; value: number; min: number; max: number; step?: number;
  onChange: (v: number) => void; description?: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-baseline">
        <span className="text-xs text-zinc-300">{label}</span>
        <span className="text-xs font-mono text-zinc-400 tabular-nums">{value}</span>
      </div>
      {description && <p className="text-[10px] text-zinc-600 leading-tight">{description}</p>}
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1 rounded accent-indigo-500 cursor-pointer" />
    </div>
  );
}

/* ── 설정 패널 ── */
export function SettingsPanel({ settings, onClose, onChange, onReset }: {
  settings: AppSettings;
  onClose: () => void;
  onChange: (key: keyof AppSettings, value: AppSettings[keyof AppSettings]) => void;
  onReset: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex">
      {/* 배경 오버레이 */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* 패널 */}
      <div className="relative ml-64 w-[420px] h-full bg-[#141414] border-r border-white/10 overflow-y-auto flex flex-col shadow-2xl">
        {/* 헤더 */}
        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-4 bg-[#141414] border-b border-white/10">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
            </svg>
            <span className="text-white font-semibold text-sm">고급 설정</span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={onReset}
              className="text-xs text-zinc-500 hover:text-zinc-300 px-2 py-1 rounded hover:bg-white/10 transition-colors">
              기본값으로
            </button>
            <button onClick={onClose} className="text-zinc-500 hover:text-white transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="flex-1 px-5 py-4 space-y-6">

          {/* 샘플링 */}
          <section>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3">샘플링</h3>
            <div className="space-y-4">
              <Slider label="Temperature" value={settings.temperature} min={0} max={2} step={0.01}
                description="높을수록 창의적·다양, 낮을수록 일관·결정적"
                onChange={(v) => onChange("temperature", v)} />
              <Slider label="Top P" value={settings.top_p} min={0} max={1} step={0.01}
                description="누적확률 상위 P% 토큰만 선택 (nucleus sampling)"
                onChange={(v) => onChange("top_p", v)} />
              <Slider label="Top K" value={settings.top_k} min={1} max={100} step={1}
                description="확률 상위 K개 토큰만 후보로 유지"
                onChange={(v) => onChange("top_k", v)} />
              <Slider label="Min P" value={settings.min_p} min={0} max={1} step={0.01}
                description="최대확률 대비 이 비율 미만 토큰 제거"
                onChange={(v) => onChange("min_p", v)} />
              <div className="space-y-1">
                <div className="flex justify-between items-baseline">
                  <span className="text-xs text-zinc-300">Seed</span>
                  <span className="text-xs font-mono text-zinc-400">{settings.seed ?? "랜덤"}</span>
                </div>
                <p className="text-[10px] text-zinc-600">고정 시 동일 입력 → 동일 출력 (재현성)</p>
                <div className="flex gap-2">
                  <input type="number" value={settings.seed ?? ""} placeholder="없음 (랜덤)"
                    onChange={(e) => onChange("seed", e.target.value === "" ? null : parseInt(e.target.value))}
                    className="flex-1 bg-[#1e1e1e] border border-white/10 text-zinc-300 text-xs px-2 py-1.5 rounded outline-none focus:border-indigo-500" />
                  {settings.seed !== null && (
                    <button onClick={() => onChange("seed", null)}
                      className="text-xs text-zinc-500 hover:text-white px-2 py-1 rounded hover:bg-white/10 transition-colors">
                      초기화
                    </button>
                  )}
                </div>
              </div>
            </div>
          </section>

          <div className="border-t border-white/5" />

          {/* 반복 제어 */}
          <section>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3">반복 제어</h3>
            <div className="space-y-4">
              <Slider label="Repeat Penalty" value={settings.repeat_penalty} min={1.0} max={2.0} step={0.01}
                description="이미 나온 토큰 재등장 억제"
                onChange={(v) => onChange("repeat_penalty", v)} />
              <Slider label="Repeat Last N" value={settings.repeat_last_n} min={0} max={128} step={1}
                description="반복 패널티를 적용할 이전 토큰 범위"
                onChange={(v) => onChange("repeat_last_n", v)} />
              <Slider label="Presence Penalty" value={settings.presence_penalty} min={-2} max={2} step={0.01}
                description="등장한 적 있는 토큰 전체에 패널티"
                onChange={(v) => onChange("presence_penalty", v)} />
              <Slider label="Frequency Penalty" value={settings.frequency_penalty} min={-2} max={2} step={0.01}
                description="등장 빈도에 비례해 패널티 (중복 문장 억제)"
                onChange={(v) => onChange("frequency_penalty", v)} />
            </div>
          </section>

          <div className="border-t border-white/5" />

          {/* 생성 제어 */}
          <section>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3">생성 제어</h3>
            <div className="space-y-4">
              <div className="space-y-1">
                <div className="flex justify-between items-baseline">
                  <span className="text-xs text-zinc-300">응답 제한 시간</span>
                  <span className="text-xs font-mono text-zinc-400">
                    {settings.request_timeout_seconds}초 ({Math.round(settings.request_timeout_seconds / 60)}분)
                  </span>
                </div>
                <p className="text-[10px] text-zinc-600">이 시간을 넘기면 Ollama 응답 대기를 중단합니다. 기본값은 300초입니다.</p>
                <input type="number" min={10} max={900} step={10} value={settings.request_timeout_seconds}
                  onChange={(e) => onChange("request_timeout_seconds", Math.min(Math.max(parseInt(e.target.value) || 300, 10), 900))}
                  className="w-full bg-[#1e1e1e] border border-white/10 text-zinc-300 text-xs px-2 py-1.5 rounded outline-none focus:border-indigo-500" />
              </div>
              <div className="space-y-1">
                <div className="flex justify-between items-baseline">
                  <span className="text-xs text-zinc-300">Max Tokens</span>
                  <span className="text-xs font-mono text-zinc-400">{settings.num_predict === -1 ? "무제한" : settings.num_predict}</span>
                </div>
                <p className="text-[10px] text-zinc-600">최대 생성 토큰 수 (-1 = 무제한)</p>
                <input type="number" min={-1} value={settings.num_predict}
                  onChange={(e) => onChange("num_predict", parseInt(e.target.value) || -1)}
                  className="w-full bg-[#1e1e1e] border border-white/10 text-zinc-300 text-xs px-2 py-1.5 rounded outline-none focus:border-indigo-500" />
              </div>
              <Slider label="Context Size" value={settings.num_ctx} min={512} max={32768} step={512}
                description="LLM에 전달할 컨텍스트 윈도우 토큰 수"
                onChange={(v) => onChange("num_ctx", v)} />
            </div>
          </section>

          <div className="border-t border-white/5" />

          {/* 하드웨어 */}
          <section>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3">하드웨어 <span className="text-zinc-700 normal-case font-normal tracking-normal">(GTX 1080 8GB)</span></h3>
            <div className="space-y-4">
              <div className="space-y-1">
                <div className="flex justify-between items-baseline">
                  <span className="text-xs text-zinc-300">GPU Layers</span>
                  <span className="text-xs font-mono text-zinc-400">{settings.num_gpu === -1 ? "자동" : settings.num_gpu}</span>
                </div>
                <p className="text-[10px] text-zinc-600">GPU에 올릴 레이어 수 (-1 = 전체 자동)</p>
                <input type="number" min={-1} value={settings.num_gpu}
                  onChange={(e) => onChange("num_gpu", parseInt(e.target.value))}
                  className="w-full bg-[#1e1e1e] border border-white/10 text-zinc-300 text-xs px-2 py-1.5 rounded outline-none focus:border-indigo-500" />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs text-zinc-300">Low VRAM 모드</span>
                  <p className="text-[10px] text-zinc-600">VRAM 절약 (GTX 1080 8GB 권장)</p>
                </div>
                <button onClick={() => onChange("low_vram", !settings.low_vram)}
                  className={`w-10 h-5 rounded-full transition-colors ${settings.low_vram ? "bg-indigo-500" : "bg-zinc-700"}`}>
                  <span className={`block w-4 h-4 bg-white rounded-full mx-0.5 transition-transform ${settings.low_vram ? "translate-x-5" : "translate-x-0"}`} />
                </button>
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs text-zinc-300">FP16 KV Cache</span>
                  <p className="text-[10px] text-zinc-600">KV캐시 fp16 사용 → 메모리 절반</p>
                </div>
                <button onClick={() => onChange("f16_kv", !settings.f16_kv)}
                  className={`w-10 h-5 rounded-full transition-colors ${settings.f16_kv ? "bg-indigo-500" : "bg-zinc-700"}`}>
                  <span className={`block w-4 h-4 bg-white rounded-full mx-0.5 transition-transform ${settings.f16_kv ? "translate-x-5" : "translate-x-0"}`} />
                </button>
              </div>
            </div>
          </section>

          <div className="border-t border-white/5" />

          {/* Hybrid RAG */}
          <section>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3">Hybrid RAG</h3>
            <div className="space-y-4">
              <Slider label="검색 청크 수 (Top K)" value={settings.rag_top_k} min={1} max={20} step={1}
                description="pgvector 의미 검색과 Elasticsearch 키워드 검색을 합친 결과 수"
                onChange={(v) => onChange("rag_top_k", v)} />
            </div>
          </section>

          <div className="border-t border-white/5" />

          {/* 웹 검색 */}
          <section>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3">웹 검색 (DuckDuckGo)</h3>
            <div className="space-y-4">
              <Slider label="검색 결과 수" value={settings.web_max_results} min={1} max={10} step={1}
                description="DuckDuckGo 검색 반환 결과 수"
                onChange={(v) => onChange("web_max_results", v)} />
            </div>
          </section>

        </div>
      </div>
    </div>
  );
}

