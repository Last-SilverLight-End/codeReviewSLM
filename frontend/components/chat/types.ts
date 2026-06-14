import type { ModelOptions } from "@/lib/api";

export type RagRef = { filename: string; chunk_type: string; name: string; start_line: number; end_line: number; };
export type WebRef = { title: string; url: string; snippet: string; };

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  filename?: string;
  loading?: boolean;
  reviewId?: number;
  reviewStatus?: string;
  statusMsg?: string;
  thinkContent?: string;
  thinkDone?: boolean;
  ragRefs?: RagRef[];
  webRefs?: WebRef[];
  note?: string | null;
  isRegenerated?: boolean;
  deletedAt?: string | null;
};

export type ProjectInfo = {
  id: number;
  name: string;
  file_count: number;
  chunk_count: number;
  created_at?: string;
};

export type AppSettings = {
  temperature: number;
  top_p: number;
  top_k: number;
  min_p: number;
  seed: number | null;
  repeat_penalty: number;
  repeat_last_n: number;
  presence_penalty: number;
  frequency_penalty: number;
  num_predict: number;
  num_ctx: number;
  num_gpu: number;
  low_vram: boolean;
  f16_kv: boolean;
  request_timeout_seconds: number;
  rag_top_k: number;
  web_max_results: number;
};

export const DEFAULT_SETTINGS: AppSettings = {
  temperature: 0.3,
  top_p: 0.9,
  top_k: 40,
  min_p: 0.0,
  seed: null,
  repeat_penalty: 1.1,
  repeat_last_n: 64,
  presence_penalty: 0.0,
  frequency_penalty: 0.0,
  num_predict: -1,
  num_ctx: 8192,
  num_gpu: -1,
  low_vram: false,
  f16_kv: false,
  request_timeout_seconds: 300,
  rag_top_k: 5,
  web_max_results: 5,
};

export const IMAGE_EXTS = ["jpg", "jpeg", "png", "gif", "webp", "bmp"];
export const CODE_FILE_EXTS = ".py,.js,.jsx,.ts,.tsx,.java,.html";
export const REVIEW_POLL_INTERVAL_MS = 3000;

export function uid() {
  return Math.random().toString(36).slice(2);
}

export function toModelOptions(s: AppSettings): ModelOptions {
  return {
    temperature: s.temperature,
    top_p: s.top_p,
    top_k: s.top_k,
    min_p: s.min_p,
    seed: s.seed,
    repeat_penalty: s.repeat_penalty,
    repeat_last_n: s.repeat_last_n,
    presence_penalty: s.presence_penalty,
    frequency_penalty: s.frequency_penalty,
    num_predict: s.num_predict,
    num_ctx: s.num_ctx,
    num_gpu: s.num_gpu,
    low_vram: s.low_vram,
    f16_kv: s.f16_kv,
    request_timeout_seconds: s.request_timeout_seconds,
  };
}
