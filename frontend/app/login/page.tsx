"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, saveToken, saveRefreshToken } from "@/lib/api";
import { ROUTES } from "@/lib/routes";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { access_token, refresh_token } = await api.login(email, password);
      saveToken(access_token);
      saveRefreshToken(refresh_token);
      router.push(ROUTES.HOME);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "로그인 실패");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#212121] px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-white/10 mb-4">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
            </svg>
          </div>
          <h1 className="text-2xl font-semibold text-white">AI Code Review</h1>
          <p className="text-zinc-400 text-sm mt-1">로컬 LLM 기반 코드 리뷰</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-sm rounded-xl px-4 py-3">
              {error}
            </div>
          )}
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            placeholder="이메일"
            className="w-full bg-[#2f2f2f] text-white placeholder-zinc-500 rounded-xl px-4 py-3 text-sm border border-white/10 focus:outline-none focus:border-white/30"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            placeholder="비밀번호"
            className="w-full bg-[#2f2f2f] text-white placeholder-zinc-500 rounded-xl px-4 py-3 text-sm border border-white/10 focus:outline-none focus:border-white/30"
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-white text-black rounded-xl py-3 text-sm font-semibold hover:bg-zinc-200 transition-colors disabled:opacity-50"
          >
            {loading ? "로그인 중..." : "계속하기"}
          </button>
        </form>

        <p className="text-center text-sm text-zinc-500 mt-6">
          계정이 없으신가요?{" "}
          <Link href="/register" className="text-white hover:underline">
            회원가입
          </Link>
        </p>
      </div>
    </div>
  );
}
