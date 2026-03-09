/**
 * API-клиент для веб-платформы SBS Archie Admin.
 * Все запросы используют cookie-based сессию (httpOnly).
 */

const BASE = '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    const detail = body.detail;
    const msg = typeof detail === 'object' ? JSON.stringify(detail) : (detail || `HTTP ${resp.status}`);
    const err = new Error(msg);
    (err as ApiError).status = resp.status;
    throw err;
  }
  return resp.json();
}

export interface ApiError extends Error {
  status: number;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface WebUser {
  telegram_id: number;
  telegram_username: string | null;
  telegram_first_name: string | null;
  telegram_last_name: string | null;
  telegram_photo_url: string | null;
  role: string;
  permissions: Array<{ module_key: string; can_view: boolean; can_edit: boolean }>;
}

export interface AuthCheckResponse {
  authenticated: boolean;
  user?: WebUser;
  dev_mode?: boolean;
}

export interface AuthConfigResponse {
  dev_mode: boolean;
  bot_id: string;
  bot_username?: string;
  password_auth_enabled?: boolean;
}

export interface AuthResponse {
  success: boolean;
  user: WebUser | null;
  session_token: string | null;
  message: string;
}

export interface TelegramAuthData {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
}

export interface PasswordLoginData {
  login: string;
  password: string;
}

export interface LocalAccount {
  id: number;
  login: string;
  principal_telegram_id: number;
  linked_telegram_id: number | null;
  display_name: string | null;
  is_active: boolean;
  failed_attempts: number;
  locked_until: string | null;
  created_at: string | null;
  updated_at: string | null;
  role: string;
}

// ---------------------------------------------------------------------------
// Expert Validation
// ---------------------------------------------------------------------------

export interface ChainMessage {
  telegram_message_id: number;
  sender_name: string | null;
  sender_id: number | null;
  message_text: string | null;
  caption: string | null;
  image_description: string | null;
  has_image: boolean;
  reply_to_message_id: number | null;
  message_date: number;
  is_question: boolean | null;
  question_confidence: number | null;
}

export interface QAPairDetail {
  id: number;
  question_text: string;
  answer_text: string;
  question_message_id: number | null;
  answer_message_id: number | null;
  group_id: number | null;
  group_title: string | null;
  extraction_type: string;
  confidence: number;
  llm_model_used: string | null;
  llm_request_payload: string | null;
  created_at: string | null;
  approved: number;
  expert_status: string | null;
  expert_validated_at: string | null;
  chain_messages: ChainMessage[];
  existing_verdict: string | null;
  existing_comment: string | null;
}

export interface ExpertValidationStats {
  total_pairs: number;
  validated_pairs: number;
  approved_pairs: number;
  rejected_pairs: number;
  skipped_pairs: number;
  unvalidated_pairs: number;
  approval_rate: number;
}

export interface QAPairListResponse {
  pairs: QAPairDetail[];
  total: number;
  page: number;
  page_size: number;
  stats: ExpertValidationStats;
}

export interface GroupInfo {
  group_id: number;
  group_title: string | null;
  pair_count: number;
  validated_count: number;
}

export interface ModuleInfo {
  key: string;
  name: string;
  icon: string;
  description: string;
  api_prefix: string;
  can_edit: boolean;
  external_url?: string;
}

// ---------------------------------------------------------------------------
// GK Knowledge — Stats
// ---------------------------------------------------------------------------

export interface GKOverviewStats {
  total_messages: number;
  total_qa_pairs: number;
  total_responder_entries: number;
  total_images: number;
  messages_with_questions: number;
  qa_pairs_approved: number;
  qa_pairs_rejected: number;
  qa_pairs_validated: number;
  qa_pairs_unvalidated: number;
  qa_pairs_vector_indexed: number;
}

export interface GKTimelineEntry {
  date: string;
  messages: number;
  qa_pairs: number;
}

export interface GKConfidenceBucket {
  range_label: string;
  count: number;
}

// ---------------------------------------------------------------------------
// GK Knowledge — Groups
// ---------------------------------------------------------------------------

export interface GKGroup {
  group_id: number;
  group_title: string | null;
  message_count: number;
  sender_count: number;
  question_pct: number;
  pair_count: number;
  validated_count: number;
  first_message_date: string | null;
  last_message_date: string | null;
}

export interface GKGroupDetailStats {
  group_id: number;
  group_title: string | null;
  message_count: number;
  sender_count: number;
  pair_count: number;
  validated_count: number;
  qa_thread_reply: number;
  qa_llm_inferred: number;
  responder_count: number;
  image_count: number;
}

// ---------------------------------------------------------------------------
// GK Knowledge — Responder
// ---------------------------------------------------------------------------

export interface GKResponderEntry {
  id: number;
  group_id: number;
  group_title: string | null;
  question_text: string | null;
  answer_text: string | null;
  confidence: number;
  dry_run: boolean;
  responded_at: string | null;
  matched_qa_pair_id: number | null;
}

export interface GKResponderSummary {
  total_entries: number;
  dry_run_count: number;
  live_count: number;
  avg_confidence: number;
}

// ---------------------------------------------------------------------------
// GK Knowledge — Images
// ---------------------------------------------------------------------------

export interface GKImageQueueStatus {
  pending: number;
  processing: number;
  done: number;
  error: number;
}

export interface GKImageQueueItem {
  id: number;
  group_id: number;
  message_id: number;
  status: number;
  status_label: string;
  file_path: string | null;
  image_description: string | null;
  created_at: string | null;
  updated_at: string | null;
}

// ---------------------------------------------------------------------------
// GK Knowledge — Prompt Tester
// ---------------------------------------------------------------------------

export interface GKPrompt {
  id: number;
  label: string;
  user_prompt: string;
  system_prompt?: string;
  extraction_type: string;
  model_name: string | null;
  temperature: number;
  is_active: boolean;
  created_at: string | null;
}

export interface GKPromptSession {
  id: number;
  name: string;
  status: string;
  prompt_ids: number[];
  prompt_count?: number;
  judge_mode: string;
  source_group_id: number | null;
  source_date_from: string | null;
  source_date_to: string | null;
  chains_count?: number;
  message_count?: number;
  generation_count?: number;
  expected_generations?: number;
  generation_progress_pct?: number;
  total_comparisons?: number;
  expected_comparisons?: number;
  voted_count?: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface GKComparison {
  has_more: boolean;
  comparison_id?: number;
  generation_a_text?: string;
  generation_b_text?: string;
  source_context?: string;
}

export interface GKSessionResults {
  session_id: number;
  total_comparisons: number;
  voted_comparisons: number;
  prompts: Array<{
    prompt_id: number;
    label: string;
    elo: number;
    wins: number;
    losses: number;
    ties: number;
    win_rate: number;
  }>;
}

export interface GKSupportedModelsResponse {
  models: string[];
  default_model: string | null;
}

// ---------------------------------------------------------------------------
// GK Knowledge — Search Playground
// ---------------------------------------------------------------------------

export interface GKSearchResult {
  question_text?: string;
  answer_text?: string;
  question: string;
  answer: string;
  score?: number;
  confidence: number;
  bm25_score: number;
  vector_score: number;
  rrf_score: number;
  qa_pair_id: number;
}

export interface GKSearchAnswerPreview {
  raw_answer_text: string | null;
  final_answer_text: string | null;
  confidence: number | null;
  would_send: boolean;
  threshold: number;
  primary_source_link: string | null;
  source_pair_ids: number[];
  source_message_links: string[];
}

export interface GKSearchResponse {
  query: string;
  results: GKSearchResult[];
  result_count: number;
  answer_preview: GKSearchAnswerPreview;
}

// ---------------------------------------------------------------------------
// API methods
// ---------------------------------------------------------------------------

export const api = {
  // Auth
  checkAuth: () =>
    request<AuthCheckResponse>('/api/auth/check'),

  getAuthConfig: () =>
    request<AuthConfigResponse>('/api/auth/config'),

  telegramAuth: (data: TelegramAuthData) =>
    request<AuthResponse>('/api/auth/telegram', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  passwordLogin: (data: PasswordLoginData) =>
    request<AuthResponse>('/api/auth/password-login', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  devLogin: (telegramId: number, firstName: string = 'Dev') =>
    request<AuthResponse>('/api/auth/dev-login', {
      method: 'POST',
      body: JSON.stringify({ telegram_id: telegramId, first_name: firstName }),
    }),

  logout: () =>
    request<{ message: string }>('/api/auth/logout', { method: 'POST' }),

  getMe: () =>
    request<WebUser>('/api/auth/me'),

  // Modules
  listModules: () =>
    request<ModuleInfo[]>('/api/modules'),

  // Expert Validation (under GK Knowledge)
  listPairs: (params: {
    page?: number;
    page_size?: number;
    group_id?: number | null;
    extraction_type?: string | null;
    question_text?: string | null;
    expert_status?: string | null;
    min_confidence?: number | null;
    max_confidence?: number | null;
    review_low_confidence_first?: boolean;
    sort_by?: string;
    sort_order?: string;
  }) => {
    const searchParams = new URLSearchParams();
    if (params.page) searchParams.set('page', String(params.page));
    if (params.page_size) searchParams.set('page_size', String(params.page_size));
    if (params.group_id) searchParams.set('group_id', String(params.group_id));
    if (params.extraction_type) searchParams.set('extraction_type', params.extraction_type);
    if (params.question_text) searchParams.set('question_text', params.question_text);
    if (params.expert_status) searchParams.set('expert_status', params.expert_status);
    if (params.min_confidence != null) searchParams.set('min_confidence', String(params.min_confidence));
    if (params.max_confidence != null) searchParams.set('max_confidence', String(params.max_confidence));
    if (params.review_low_confidence_first) searchParams.set('review_low_confidence_first', 'true');
    if (params.sort_by) searchParams.set('sort_by', params.sort_by);
    if (params.sort_order) searchParams.set('sort_order', params.sort_order);
    return request<QAPairListResponse>(`/api/gk-knowledge/expert-validation/pairs?${searchParams}`);
  },

  getPairDetail: (pairId: number) =>
    request<QAPairDetail>(`/api/gk-knowledge/expert-validation/pairs/${pairId}`),

  getChain: (pairId: number) =>
    request<ChainMessage[]>(`/api/gk-knowledge/expert-validation/pairs/${pairId}/chain`),

  validatePair: (data: { qa_pair_id: number; verdict: string; comment?: string }) =>
    request<{ validation_id: number; qa_pair_id: number; verdict: string; message: string }>(
      '/api/gk-knowledge/expert-validation/validate',
      { method: 'POST', body: JSON.stringify(data) },
    ),

  getValidationStats: (groupId?: number) => {
    const params = groupId ? `?group_id=${groupId}` : '';
    return request<ExpertValidationStats>(`/api/gk-knowledge/expert-validation/stats${params}`);
  },

  getEVGroups: () =>
    request<GroupInfo[]>('/api/gk-knowledge/expert-validation/groups'),

  getPairHistory: (pairId: number) =>
    request<Array<{ expert_telegram_id: number; verdict: string; comment: string | null; created_at: string; updated_at: string }>>(
      `/api/gk-knowledge/expert-validation/pairs/${pairId}/history`,
    ),

  // GK Knowledge — Stats
  gkStatsOverview: (groupId?: number) => {
    const params = groupId ? `?group_id=${groupId}` : '';
    return request<GKOverviewStats>(`/api/gk-knowledge/stats/overview${params}`);
  },

  gkStatsTimeline: (groupId?: number, days: number = 30) => {
    const searchParams = new URLSearchParams();
    if (groupId) searchParams.set('group_id', String(groupId));
    searchParams.set('days', String(days));
    return request<{ dates: GKTimelineEntry[] }>(`/api/gk-knowledge/stats/timeline?${searchParams}`);
  },

  gkStatsDistribution: (groupId?: number) => {
    const params = groupId ? `?group_id=${groupId}` : '';
    return request<GKConfidenceBucket[]>(`/api/gk-knowledge/stats/distribution${params}`);
  },

  // GK Knowledge — QA Pairs
  gkQAPairs: (params: {
    page?: number;
    page_size?: number;
    group_id?: number | null;
    extraction_type?: string | null;
    search_text?: string | null;
    expert_status?: string | null;
    approved?: boolean | null;
    vector_indexed?: boolean | null;
    min_confidence?: number | null;
    max_confidence?: number | null;
    sort_by?: string;
    sort_order?: string;
  }) => {
    const searchParams = new URLSearchParams();
    if (params.page) searchParams.set('page', String(params.page));
    if (params.page_size) searchParams.set('page_size', String(params.page_size));
    if (params.group_id) searchParams.set('group_id', String(params.group_id));
    if (params.extraction_type) searchParams.set('extraction_type', params.extraction_type);
    if (params.search_text) searchParams.set('search_text', params.search_text);
    if (params.expert_status) searchParams.set('expert_status', params.expert_status);
    if (params.approved != null) searchParams.set('approved', String(params.approved));
    if (params.vector_indexed != null) searchParams.set('vector_indexed', String(params.vector_indexed));
    if (params.min_confidence != null) searchParams.set('min_confidence', String(params.min_confidence));
    if (params.max_confidence != null) searchParams.set('max_confidence', String(params.max_confidence));
    if (params.sort_by) searchParams.set('sort_by', params.sort_by);
    if (params.sort_order) searchParams.set('sort_order', params.sort_order);
    return request<{ pairs: QAPairDetail[]; total: number; page: number; page_size: number }>(
      `/api/gk-knowledge/qa-pairs?${searchParams}`,
    );
  },

  gkQAPairDetail: (pairId: number) =>
    request<QAPairDetail>(`/api/gk-knowledge/qa-pairs/${pairId}`),

  // GK Knowledge — Groups
  gkGroups: () =>
    request<GKGroup[]>('/api/gk-knowledge/groups'),

  gkGroupStats: (groupId: number) =>
    request<GKGroupDetailStats>(`/api/gk-knowledge/groups/${groupId}/stats`),

  // GK Knowledge — Responder
  gkResponderLog: (params: {
    page?: number;
    page_size?: number;
    group_id?: number | null;
    dry_run?: boolean | null;
    min_confidence?: number | null;
    sort_by?: string;
    sort_order?: string;
  }) => {
    const searchParams = new URLSearchParams();
    if (params.page) searchParams.set('page', String(params.page));
    if (params.page_size) searchParams.set('page_size', String(params.page_size));
    if (params.group_id) searchParams.set('group_id', String(params.group_id));
    if (params.dry_run != null) searchParams.set('dry_run', String(params.dry_run));
    if (params.min_confidence != null) searchParams.set('min_confidence', String(params.min_confidence));
    if (params.sort_by) searchParams.set('sort_by', params.sort_by);
    if (params.sort_order) searchParams.set('sort_order', params.sort_order);
    return request<{ entries: GKResponderEntry[]; total: number; page: number; page_size: number }>(
      `/api/gk-knowledge/responder/log?${searchParams}`,
    );
  },

  gkResponderSummary: (groupId?: number) => {
    const params = groupId ? `?group_id=${groupId}` : '';
    return request<GKResponderSummary>(`/api/gk-knowledge/responder/summary${params}`);
  },

  // GK Knowledge — Images
  gkImageStatus: () =>
    request<GKImageQueueStatus>('/api/gk-knowledge/images/status'),

  gkImageList: (params: {
    page?: number;
    page_size?: number;
    status?: number | null;
    sort_order?: string;
  }) => {
    const searchParams = new URLSearchParams();
    if (params.page) searchParams.set('page', String(params.page));
    if (params.page_size) searchParams.set('page_size', String(params.page_size));
    if (params.status != null) searchParams.set('status', String(params.status));
    if (params.sort_order) searchParams.set('sort_order', params.sort_order);
    return request<{ items: GKImageQueueItem[]; total: number; page: number; page_size: number }>(
      `/api/gk-knowledge/images/list?${searchParams}`,
    );
  },

  // GK Knowledge — Prompt Tester
  gkPromptTesterSupportedModels: () =>
    request<GKSupportedModelsResponse>('/api/gk-knowledge/prompt-tester/supported-models'),

  gkPrompts: (activeOnly: boolean = true) =>
    request<GKPrompt[]>(`/api/gk-knowledge/prompt-tester/prompts?active_only=${activeOnly}`),

  gkCreatePrompt: (data: { label: string; user_prompt: string; extraction_type?: string; model_name?: string; temperature?: number }) =>
    request<{ id: number; message: string }>('/api/gk-knowledge/prompt-tester/prompts', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  gkUpdatePrompt: (promptId: number, data: Partial<{ label: string; user_prompt: string; extraction_type: string; model_name: string; temperature: number }>) =>
    request<{ message: string }>(`/api/gk-knowledge/prompt-tester/prompts/${promptId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  gkDeletePrompt: (promptId: number) =>
    request<{ message: string }>(`/api/gk-knowledge/prompt-tester/prompts/${promptId}`, {
      method: 'DELETE',
    }),

  gkSessions: () =>
    request<GKPromptSession[]>('/api/gk-knowledge/prompt-tester/sessions'),

  gkCreateSession: (data: { name: string; prompt_ids: number[]; chains_count?: number; judge_mode?: string; source_group_id?: number; source_date_from?: string; source_date_to?: string }) =>
    request<{ id: number; message: string }>('/api/gk-knowledge/prompt-tester/sessions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  gkGetSession: (sessionId: number) =>
    request<GKPromptSession>(`/api/gk-knowledge/prompt-tester/sessions/${sessionId}`),

  gkGetNextComparison: (sessionId: number) =>
    request<GKComparison>(`/api/gk-knowledge/prompt-tester/sessions/${sessionId}/compare`),

  gkVote: (sessionId: number, data: { comparison_id: number; winner: string }) =>
    request<{ message: string }>(`/api/gk-knowledge/prompt-tester/sessions/${sessionId}/vote`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  gkSessionResults: (sessionId: number) =>
    request<GKSessionResults>(`/api/gk-knowledge/prompt-tester/sessions/${sessionId}/results`),

  gkAbandonSession: (sessionId: number) =>
    request<{ message: string }>(`/api/gk-knowledge/prompt-tester/sessions/${sessionId}/abandon`, {
      method: 'POST',
    }),

  gkSessionGenerations: (sessionId: number) =>
    request<Array<{ id: number; prompt_id: number; prompt_label: string; generated_text: string; generated_at: string }>>(`/api/gk-knowledge/prompt-tester/sessions/${sessionId}/generations`),

  // GK Knowledge — Search
  gkSearch: (query: string, topK: number = 10) =>
    request<GKSearchResponse>(
      '/api/gk-knowledge/search/query',
      { method: 'POST', body: JSON.stringify({ query, top_k: topK }) },
    ),

  // Admin: Roles
  listRoles: () =>
    request<Array<{ telegram_id: number; role: string; created_at: string; updated_at: string; created_by: number | null }>>(
      '/api/admin/roles',
    ),

  setRole: (telegramId: number, role: string) =>
    request<{ message: string }>(
      `/api/admin/roles?telegram_id=${telegramId}&role=${role}`,
      { method: 'POST' },
    ),

  deleteRole: (telegramId: number) =>
    request<{ message: string }>(`/api/admin/roles/${telegramId}`, { method: 'DELETE' }),

  // Admin: Local password accounts
  listLocalAccounts: () =>
    request<LocalAccount[]>('/api/admin/local-accounts'),

  createLocalAccount: (data: {
    login: string;
    password: string;
    role: string;
    linked_telegram_id?: number;
    display_name?: string;
    is_active?: boolean;
  }) =>
    request<LocalAccount>('/api/admin/local-accounts', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  resetLocalAccountPassword: (localAccountId: number, newPassword: string) =>
    request<{ message: string }>(`/api/admin/local-accounts/${localAccountId}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword }),
    }),

  activateLocalAccount: (localAccountId: number, isActive: boolean) =>
    request<{ message: string }>(
      `/api/admin/local-accounts/${localAccountId}/activate?is_active=${isActive ? 'true' : 'false'}`,
      { method: 'POST' },
    ),

  // -----------------------------------------------------------------------
  // Process Manager
  // -----------------------------------------------------------------------

  /** Все процессы, сгруппированные по категориям. */
  pmListProcesses: () =>
    request<{ categories: Record<string, ProcessStatusInfo[]> }>('/api/process-manager/processes'),

  /** Статус одного процесса. */
  pmGetProcess: (key: string) =>
    request<ProcessStatusInfo>(`/api/process-manager/processes/${key}`),

  /** Реестр процесса: флаги и пресеты. */
  pmGetRegistry: (key: string) =>
    request<ProcessRegistryInfo>(`/api/process-manager/processes/${key}/registry`),

  /** Запустить процесс. */
  pmStartProcess: (key: string, body: { preset?: string; flags?: string[]; form_data?: Record<string, unknown>; persist?: boolean }) =>
    request<ProcessStatusInfo>(`/api/process-manager/processes/${key}/start`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  /** Остановить процесс. */
  pmStopProcess: (key: string) =>
    request<ProcessStatusInfo>(`/api/process-manager/processes/${key}/stop`, {
      method: 'POST',
    }),

  /** Перезапустить процесс. */
  pmRestartProcess: (key: string, body: { preset?: string; flags?: string[] }) =>
    request<ProcessStatusInfo>(`/api/process-manager/processes/${key}/restart`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  /** История запусков процесса. */
  pmGetHistory: (key: string, page = 1, pageSize = 20) =>
    request<ProcessHistoryResponse>(
      `/api/process-manager/processes/${key}/history?page=${page}&page_size=${pageSize}`,
    ),

  /** Общая история. */
  pmGetAllHistory: (page = 1, pageSize = 20, processKey?: string, status?: string) => {
    let url = `/api/process-manager/history?page=${page}&page_size=${pageSize}`;
    if (processKey) url += `&process_key=${processKey}`;
    if (status) url += `&status=${status}`;
    return request<ProcessHistoryResponse>(url);
  },

  /** Вывод процесса (buffer). */
  pmGetOutput: (key: string, lastN = 200) =>
    request<{ lines: Array<{ timestamp: string; line: string }>; total_lines: number }>(
      `/api/process-manager/processes/${key}/output?last_n=${lastN}`,
    ),
};

// ---------------------------------------------------------------------------
// Process Manager: WebSocket helper
// ---------------------------------------------------------------------------

/**
 * Подключиться к WebSocket стриминга логов процесса.
 * Возвращает объект с методами для управления соединением.
 */
export function connectProcessLogs(
  processKey: string,
  onMessage: (entry: { timestamp: string; line: string }) => void,
  onClose?: () => void,
) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${window.location.host}/api/process-manager/processes/${processKey}/logs`;
  let ws: WebSocket | null = new WebSocket(url);
  let closed = false;

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'heartbeat') return;
      onMessage(data);
    } catch { /* ignore parse errors */ }
  };

  ws.onclose = () => {
    if (!closed && onClose) onClose();
  };

  ws.onerror = () => {
    // Will trigger onclose
  };

  return {
    close() {
      closed = true;
      ws?.close();
      ws = null;
    },
    get connected() {
      return ws?.readyState === WebSocket.OPEN;
    },
  };
}

// ---------------------------------------------------------------------------
// Process Manager: Types
// ---------------------------------------------------------------------------

export interface ProcessStatusInfo {
  key: string;
  name: string;
  icon: string;
  category: string;
  process_type: 'daemon' | 'one_shot';
  status: 'running' | 'stopped' | 'crashed' | 'starting' | 'stopping' | 'unknown';
  pid: number | null;
  uptime_seconds: number | null;
  current_flags: string[] | null;
  current_preset: string | null;
  started_at: string | null;
  started_by: number | null;
  exit_code: number | null;
  auto_restart: boolean;
  singleton: boolean;
  description: string;
}

export interface FlagDef {
  name: string;
  flag_type: 'bool' | 'int' | 'string' | 'choice';
  description: string;
  default: unknown;
  choices: string[] | null;
  mutually_exclusive_group: string | null;
  required: boolean;
}

export interface PresetDef {
  name: string;
  description: string;
  flags: string[];
  icon: string;
  requires_form: boolean;
  form_type: string | null;
  hidden: boolean;
}

export interface ProcessRegistryInfo {
  key: string;
  name: string;
  icon: string;
  category: string;
  process_type: 'daemon' | 'one_shot';
  description: string;
  singleton: boolean;
  auto_restart: boolean;
  flags: FlagDef[];
  presets: PresetDef[];
}

export interface ProcessRunRecord {
  id: number;
  process_key: string;
  pid: number | null;
  flags: string[] | null;
  preset_name: string | null;
  started_by: number | null;
  started_at: string | null;
  stopped_at: string | null;
  exit_code: number | null;
  status: string;
  stop_reason: string | null;
}

export interface ProcessHistoryResponse {
  runs: ProcessRunRecord[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// Process Manager: Groups
// ---------------------------------------------------------------------------

export interface GroupEntry {
  id: number;
  title: string;
}

export interface TestTargetGroup {
  id: number;
  title: string;
  participants?: number | null;
}

export interface GKGroupsConfig {
  groups: GroupEntry[];
  test_target_group: TestTargetGroup | null;
}

export interface HelperGroupsConfig {
  groups: GroupEntry[];
}

export interface CollectedGroupInfo {
  group_id: number;
  group_title: string | null;
  message_count: number;
  first_message: string | null;
  last_message: string | null;
}

export const groupsApi = {
  /** GK-группы: получить. */
  getGKGroups: () =>
    request<GKGroupsConfig>('/api/process-manager/groups/gk'),

  /** GK-группы: полностью обновить. */
  updateGKGroups: (config: GKGroupsConfig) =>
    request<GKGroupsConfig>('/api/process-manager/groups/gk', {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  /** GK-группы: добавить. */
  addGKGroup: (group: { id: number; title: string }) =>
    request<{ groups: GroupEntry[] }>('/api/process-manager/groups/gk/add', {
      method: 'POST',
      body: JSON.stringify(group),
    }),

  /** GK-группы: удалить. */
  removeGKGroup: (groupId: number) =>
    request<{ groups: GroupEntry[] }>(`/api/process-manager/groups/gk/${groupId}`, {
      method: 'DELETE',
    }),

  /** GK test target group: установить. */
  setGKTestTarget: (group: TestTargetGroup) =>
    request<{ test_target_group: TestTargetGroup }>('/api/process-manager/groups/gk/test-target', {
      method: 'PUT',
      body: JSON.stringify(group),
    }),

  /** GK test target group: очистить. */
  clearGKTestTarget: () =>
    request<{ test_target_group: null }>('/api/process-manager/groups/gk/test-target', {
      method: 'DELETE',
    }),

  /** Helper-группы: получить. */
  getHelperGroups: () =>
    request<HelperGroupsConfig>('/api/process-manager/groups/helper'),

  /** Helper-группы: полностью обновить. */
  updateHelperGroups: (config: HelperGroupsConfig) =>
    request<HelperGroupsConfig>('/api/process-manager/groups/helper', {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  /** Helper-группы: добавить. */
  addHelperGroup: (group: { id: number; title: string }) =>
    request<{ groups: GroupEntry[] }>('/api/process-manager/groups/helper/add', {
      method: 'POST',
      body: JSON.stringify(group),
    }),

  /** Helper-группы: удалить. */
  removeHelperGroup: (groupId: number) =>
    request<{ groups: GroupEntry[] }>(`/api/process-manager/groups/helper/${groupId}`, {
      method: 'DELETE',
    }),

  /** Собранные группы из БД. */
  getCollectedGroups: () =>
    request<CollectedGroupInfo[]>('/api/process-manager/groups/collected'),
};
