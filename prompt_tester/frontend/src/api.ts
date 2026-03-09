/** API-клиент для тестера промптов. */

const APP_PREFIX = window.location.pathname.startsWith('/prompt-tester') ? '/prompt-tester' : '';
const BASE = APP_PREFIX;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    const detail = body.detail;
    // Если detail — объект (JSON), передаём как строку для парсинга в компоненте
    const msg = typeof detail === 'object' ? JSON.stringify(detail) : (detail || `HTTP ${resp.status}`);
    throw new Error(msg);
  }
  return resp.json();
}

// ---- Промпты ----

export interface Prompt {
  id: number;
  label: string;
  system_prompt_template: string;
  user_message: string;
  model_name: string | null;
  temperature: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  usage_count: number;
}

export interface PromptCreatePayload {
  label: string;
  system_prompt_template: string;
  user_message: string;
  model_name?: string | null;
  temperature?: number | null;
}

export interface PromptUpdatePayload {
  label?: string;
  system_prompt_template?: string;
  user_message?: string;
  model_name?: string | null;
  temperature?: number | null;
  clear_model_name?: boolean;
  clear_temperature?: boolean;
}

export const api = {
  // Prompts
  listPrompts: (activeOnly = true) =>
    request<Prompt[]>(`/api/prompts?active_only=${activeOnly}`),

  getPrompt: (id: number) =>
    request<Prompt>(`/api/prompts/${id}`),

  createPrompt: (data: PromptCreatePayload) =>
    request<{ id: number }>('/api/prompts', { method: 'POST', body: JSON.stringify(data) }),

  updatePrompt: (id: number, data: PromptUpdatePayload) =>
    request<{ message: string }>(`/api/prompts/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  deletePrompt: (id: number) =>
    request<{ message: string }>(`/api/prompts/${id}`, { method: 'DELETE' }),

  duplicatePrompt: (id: number) =>
    request<{ id: number }>(`/api/prompts/${id}/duplicate`, { method: 'POST' }),

  previewPrompt: (id: number) =>
    request<{ document_name: string; rendered_system_prompt: string; user_message: string; excerpt_length: number }>(
      `/api/prompts/${id}/preview`
    ),

  // Sessions
  listSessions: () =>
    request<SessionListItem[]>('/api/sessions'),

  createSession: (data: { name: string; prompt_ids: number[]; document_count: number; judge_mode: string }) =>
    request<{ id: number; total_comparisons: number; document_count: number }>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getSession: (id: number) =>
    request<SessionDetail>(`/api/sessions/${id}`),

  getNextComparison: (sessionId: number) =>
    request<ComparisonData>(`/api/sessions/${sessionId}/next`),

  getDocumentContent: (sessionId: number, documentId: number) =>
    request<DocumentContent>(`/api/sessions/${sessionId}/document/${documentId}`),

  vote: (sessionId: number, data: { generation_a_id: number; generation_b_id: number; winner: string }) =>
    request<{ vote_id: number }>(`/api/sessions/${sessionId}/vote`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getSessionResults: (sessionId: number) =>
    request<SessionResultsData>(`/api/sessions/${sessionId}/results`),

  getAggregateResults: () =>
    request<AggregateResultsData>('/api/results/aggregate'),
};

// ---- Types ----

export interface SessionListItem {
  id: number;
  name: string;
  status: string;
  total_comparisons: number;
  completed_comparisons: number;
  judge_mode: string;
  prompt_count: number;
  document_count: number;
  created_at: string;
}

export interface SessionDetail {
  id: number;
  name: string;
  status: string;
  prompt_ids_snapshot: number[];
  prompts_config_snapshot: PromptConfig[];
  document_ids: number[];
  total_comparisons: number;
  completed_comparisons: number;
  judge_mode: string;
  created_at: string;
  updated_at: string;
}

export interface PromptConfig {
  id: number;
  label: string;
  system_prompt_template: string;
  user_message: string;
  model_name: string | null;
  temperature: number | null;
}

export interface ComparisonData {
  document_id?: number;
  document_name?: string;
  generation_a?: { id: number; summary_text: string };
  generation_b?: { id: number; summary_text: string };
  progress: { completed: number; total: number };
  has_more: boolean;
}

export interface DocumentContent {
  document_id: number;
  filename: string;
  source_type: string;
  chunks: string[];
  chunks_count: number;
  total_chars: number;
}

export interface PromptResult {
  prompt_id: number;
  label: string;
  model_name: string | null;
  temperature: number | null;
  wins: number;
  losses: number;
  ties: number;
  skips: number;
  win_rate: number;
  elo: number;
}

export interface SessionResultsData {
  session_id: number;
  session_name: string;
  status: string;
  human_results: PromptResult[];
  llm_results: PromptResult[];
  document_breakdown: Array<{
    document_id: number;
    comparisons: Array<{
      prompt_a_label: string;
      prompt_b_label: string;
      winner: string;
    }>;
  }>;
}

export interface AggregateResultsData {
  prompt_results: PromptResult[];
  sessions_count: number;
  total_votes: number;
}
