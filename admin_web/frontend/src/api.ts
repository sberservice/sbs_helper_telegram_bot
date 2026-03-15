/**
 * API-клиент для веб-платформы SBS Archie Admin.
 * Все запросы используют cookie-based сессию (httpOnly).
 */

const BASE = '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isFormDataBody = typeof FormData !== 'undefined' && options?.body instanceof FormData;
  const mergedHeaders: HeadersInit = isFormDataBody
    ? { ...(options?.headers || {}) }
    : { 'Content-Type': 'application/json', ...(options?.headers || {}) };

  const resp = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: mergedHeaders,
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

// ---------------------------------------------------------------------------
// GK Terms
// ---------------------------------------------------------------------------

export interface TermDetail {
  id: number;
  group_id: number;
  term: string;
  definition: string | null;
  has_definition: boolean;
  source: string;
  status: string;
  confidence: number | null;
  expert_status: string | null;
  scan_batch_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  group_title: string | null;
  existing_verdict: string | null;
  existing_comment: string | null;
  message_count: number;
  message_count_updated_at: string | null;
}

export interface TermValidationStats {
  total: number;
  pending: number;
  approved: number;
  rejected: number;
  with_definition: number;
  without_definition: number;
}

export interface TermListResponse {
  terms: TermDetail[];
  total: number;
  page: number;
  page_size: number;
  stats: TermValidationStats;
}

export interface TermGroupInfo {
  group_id: number;
  group_title: string | null;
  term_count: number;
  pending_count: number;
}

export interface TermValidationHistoryEntry {
  expert_telegram_id: number;
  verdict: string;
  edited_term: string | null;
  edited_definition: string | null;
  comment: string | null;
  created_at: string;
  updated_at: string;
}

export interface TermUsageMessage {
  id: number;
  telegram_message_id: number;
  group_id: number;
  sender_name: string | null;
  sender_id: number | null;
  message_text: string | null;
  caption: string | null;
  image_description: string | null;
  message_date: number;
  matched_field?: 'message_text';
  matched_text?: string | null;
}

export interface TermScanStatus {
  status: string;
  batch_id: string;
  started_at?: string;
  finished_at?: string | null;
  result?: {
    scan_batch_id: string;
    terms_found: number;
    terms_stored: number;
    terms_new?: number;
    terms_updated?: number;
    terms_skipped?: number;
    batches_processed: number;
    errors: string[];
  };
  progress?: {
    stage?: string;
    message?: string;
    percent?: number;
    updated_at?: string;
    batches_processed?: number;
    total_batches?: number;
    terms_found_so_far?: number;
    terms_found?: number;
    terms_new?: number;
    terms_updated?: number;
    terms_skipped?: number;
    errors_count?: number;
  };
  progress_log?: Array<{
    stage?: string;
    message?: string;
    percent?: number;
    updated_at?: string;
    batches_processed?: number;
    total_batches?: number;
    terms_found_so_far?: number;
    terms_found?: number;
    terms_new?: number;
    terms_updated?: number;
    terms_skipped?: number;
    errors_count?: number;
  }>;
  error?: string;
}

export interface TermRecountStatus {
  task_id: string;
  group_id: number;
  status: string;
  started_at?: string;
  finished_at?: string | null;
  progress?: {
    stage?: string;
    message?: string;
    percent?: number;
    updated_at?: string;
  };
  result?: {
    group_id: number;
    terms_counted: number;
    messages_scanned: number;
    updated: number;
    status: string;
    errors?: string[];
  };
  error?: string;
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

export interface GKMessageBrowserItem {
  id: number;
  telegram_message_id: number;
  group_id: number;
  group_title: string | null;
  sender_id: number;
  sender_name: string | null;
  message_text: string | null;
  caption: string | null;
  has_image: boolean;
  image_description: string | null;
  reply_to_message_id: number | null;
  message_date: number;
  processed: boolean;
  is_question: boolean | null;
  responder_mode: 'dry_run' | 'live' | null;
  responder_confidence: number | null;
  responder_responded_at: number | null;
  is_in_chain: boolean;
  is_analyzed: boolean;
}

export interface GKMessageBrowserSender {
  sender_id: number;
  sender_name: string | null;
  message_count: number;
}

export interface GKMessageChainItem {
  group_id: number;
  telegram_message_id: number;
  sender_name: string | null;
  sender_id: number;
  message_text: string | null;
  caption: string | null;
  image_description: string | null;
  has_image: boolean;
  reply_to_message_id: number | null;
  message_date: number;
  is_question: boolean | null;
  question_confidence: number | null;
}

// ---------------------------------------------------------------------------
// GK Knowledge — Responder
// ---------------------------------------------------------------------------

export interface GKResponderEntry {
  id: number;
  group_id: number;
  group_title: string | null;
  question_message_date: string | number | null;
  question_text: string | null;
  answer_text: string | null;
  llm_request_payload: string | null;
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
  image_path?: string | null;
  file_path: string | null;
  image_description: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface GKImagePrompt {
  id: number;
  label: string;
  prompt_text: string;
  model_name: string | null;
  temperature: number;
  is_active: boolean;
  created_at: string | null;
}

export interface GKImagePromptSession {
  id: number;
  name: string;
  status: string;
  prompt_ids: number[];
  prompt_count?: number;
  source_group_id: number | null;
  source_date_from: string | null;
  source_date_to: string | null;
  image_count?: number;
  generation_count?: number;
  expected_generations?: number;
  generation_progress_pct?: number;
  total_comparisons?: number;
  expected_comparisons?: number;
  voted_count?: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface GKImageComparison {
  has_more: boolean;
  comparison_id?: number;
  image_queue_id?: number;
  image_preview_url?: string | null;
  generation_a_text?: string;
  generation_b_text?: string;
  progress_total?: number;
  progress_voted?: number;
}

export interface GKImageSessionEstimate {
  prompt_count: number;
  requested_image_count: number;
  effective_image_count: number;
  expected_comparisons: number;
  can_create: boolean;
}

export interface GKImagePromptTesterStats {
  summary: {
    sessions_total: number;
    sessions_completed: number;
    sessions_judging: number;
    sessions_generating: number;
    voted_matches: number;
    skipped_matches: number;
    prompts_total: number;
  };
  prompts: Array<{
    prompt_id: number;
    label: string;
    is_active: boolean;
    sessions_count: number;
    elo: number;
    elo_delta: number;
    wins: number;
    losses: number;
    ties: number;
    skips: number;
    matches: number;
    win_rate: number;
  }>;
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
  progress_total?: number;
  progress_voted?: number;
}

export interface GKPromptSessionEstimate {
  prompt_count: number;
  requested_chains_count: number;
  effective_chains_count: number;
  expected_comparisons: number;
  can_create: boolean;
}

export interface GKSearchProgressStage {
  key: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'error' | 'skipped';
  duration_ms?: number;
}

export interface GKSessionResults {
  session_id: number;
  total_comparisons: number;
  voted_comparisons: number;
  prompts: Array<{
    prompt_id: number;
    label: string;
    elo: number;
    elo_delta?: number;
    wins: number;
    losses: number;
    ties: number;
    skips?: number;
    matches?: number;
    score?: number;
    win_rate: number;
    loss_rate?: number;
  }>;
}

export interface GKPromptTesterStats {
  summary: {
    sessions_total: number;
    sessions_completed: number;
    sessions_judging: number;
    sessions_generating: number;
    voted_matches: number;
    skipped_matches: number;
    prompts_total: number;
  };
  prompts: Array<{
    prompt_id: number;
    label: string;
    is_active: boolean;
    sessions_count: number;
    elo: number;
    elo_delta: number;
    wins: number;
    losses: number;
    ties: number;
    skips: number;
    matches: number;
    win_rate: number;
  }>;
}

export interface RAGCorpusStatsResponse {
  documents: {
    total: number;
    active: number;
    archived: number;
    deleted: number;
    last_updated_at: string | null;
    by_source_type: Record<string, number>;
  };
  chunks: {
    total: number;
    avg_per_document: number;
    max_per_document: number;
    last_created_at: string | null;
  };
  summaries: {
    total: number;
    with_model_name: number;
    last_updated_at: string | null;
  };
  chunk_embeddings: {
    total: number;
    ready: number;
    failed: number;
    stale: number;
    last_updated_at: string | null;
  };
  summary_embeddings: {
    total: number;
    ready: number;
    failed: number;
    stale: number;
    last_updated_at: string | null;
  };
  query_log: {
    total: number;
    cache_hits: number;
    cache_hit_ratio: number;
    last_24h: number;
    last_7d: number;
    unique_users: number;
    last_query_at: string | null;
  };
  corpus_version: {
    total_versions: number;
    last_reason: string | null;
    last_created_at: string | null;
  };
}

export interface GKFinalPrompt {
  id: number;
  label: string;
  prompt_template: string;
  model_name: string | null;
  temperature: number;
  is_active: boolean;
  created_at: string | null;
}

export interface GKFinalPromptSession {
  id: number;
  name: string;
  status: string;
  prompt_ids: number[];
  questions_snapshot?: string[];
  prompt_count?: number;
  judge_mode: string;
  source_group_id: number | null;
  question_count?: number;
  generation_count?: number;
  expected_generations?: number;
  generation_progress_pct?: number;
  total_comparisons?: number;
  expected_comparisons?: number;
  voted_count?: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface GKFinalPromptSessionEstimate {
  prompt_count: number;
  requested_question_count: number;
  effective_question_count: number;
  expected_comparisons: number;
  can_create: boolean;
}

export interface GKFinalComparison {
  has_more: boolean;
  comparison_id?: number;
  generation_a_text?: string;
  generation_b_text?: string;
  source_context?: string;
  progress_total?: number;
  progress_voted?: number;
}

export interface GKFinalPromptTesterStats {
  summary: {
    sessions_total: number;
    sessions_completed: number;
    sessions_judging: number;
    sessions_generating: number;
    voted_matches: number;
    skipped_matches: number;
    prompts_total: number;
  };
  prompts: Array<{
    prompt_id: number;
    label: string;
    is_active: boolean;
    sessions_count: number;
    elo: number;
    elo_delta: number;
    wins: number;
    losses: number;
    ties: number;
    skips: number;
    matches: number;
    win_rate: number;
  }>;
}

export interface RAGDocumentListItem {
  id: number;
  filename: string;
  source_type: string;
  source_url: string | null;
  uploaded_by: number;
  status: 'active' | 'archived' | 'deleted';
  content_hash: string;
  created_at: string | null;
  updated_at: string | null;
  chunk_count: number;
  has_summary: boolean;
  summary_model_name: string | null;
  summary_updated_at: string | null;
  chunk_embeddings: {
    ready: number;
    failed: number;
    stale: number;
  };
  summary_embeddings: {
    ready: number;
    failed: number;
    stale: number;
  };
}

export interface RAGDocumentsResponse {
  items: RAGDocumentListItem[];
  page: number;
  page_size: number;
  total: number;
  stats: {
    documents_total: number;
    status_counts: {
      active: number;
      archived: number;
      deleted: number;
    };
    source_type_counts: Record<string, number>;
    total_chunks: number;
    avg_chunks_per_document: number;
    documents_with_summary: number;
    chunk_embeddings: {
      ready: number;
      failed: number;
      stale: number;
    };
    summary_embeddings: {
      ready: number;
      failed: number;
      stale: number;
    };
    last_document_updated_at: string | null;
  };
  filters: {
    q: string | null;
    status: string | null;
    source_type: string | null;
    has_summary: boolean | null;
    sort_by: string;
    sort_order: 'asc' | 'desc';
  };
}

export interface GKSupportedModelsResponse {
  models: string[];
  default_model: string | null;
}

export interface GKLLMSettingsResponse {
  text_provider: string;
  text_provider_options: string[];
  text_model_options_by_provider: Record<string, string[]>;
  text_models: {
    analysis: string;
    responder: string;
    question_detection: string;
    terms_scan: string;
  };
  image_provider: string;
  image_provider_options: string[];
  image_model_options_by_provider: Record<string, string[]>;
  image_model: string;
  main_settings: {
    responder: {
      confidence_threshold: number;
      top_k: number;
      temperature: number;
      include_llm_inferred_answers: boolean;
      exclude_low_tier_from_llm_context: boolean;
    };
    analysis: {
      question_confidence_threshold: number;
      temperature: number;
      question_detection_temperature: number;
      generate_llm_inferred_qa_pairs: boolean;
    };
    terms: {
      acronyms_max_prompt_terms: number;
      scan_temperature: number;
    };
    search: {
      hybrid_enabled: boolean;
      relevance_hints_enabled: boolean;
      candidates_per_method: number;
    };
  };
}

export interface GKLLMSettingsUpdateRequest {
  text_provider?: string;
  text_models?: Partial<{
    analysis: string;
    responder: string;
    question_detection: string;
    terms_scan: string;
  }>;
  image_provider?: string;
  image_model?: string;
  main_settings?: Partial<{
    responder: Partial<{
      confidence_threshold: number;
      top_k: number;
      temperature: number;
      include_llm_inferred_answers: boolean;
      exclude_low_tier_from_llm_context: boolean;
    }>;
    analysis: Partial<{
      question_confidence_threshold: number;
      temperature: number;
      question_detection_temperature: number;
      generate_llm_inferred_qa_pairs: boolean;
    }>;
    terms: Partial<{
      acronyms_max_prompt_terms: number;
      scan_temperature: number;
    }>;
    search: Partial<{
      hybrid_enabled: boolean;
      relevance_hints_enabled: boolean;
      candidates_per_method: number;
    }>;
  }>;
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
  confidence_reason?: string;
  fullness?: number | null;
  bm25_score: number;
  vector_score: number;
  rrf_score: number;
  qa_pair_id: number;
}

export interface GKSearchAnswerPreview {
  raw_answer_text: string | null;
  final_answer_text: string | null;
  confidence: number | null;
  confidence_reason: string | null;
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
  progress_stages?: GKSearchProgressStage[];
  duration_ms?: number;
}

// ---------------------------------------------------------------------------
// GK Knowledge — QA Analyzer Sandbox
// ---------------------------------------------------------------------------

export interface QAAnalyzerSearchMessage {
  id: number;
  telegram_message_id: number;
  group_id: number;
  group_title: string | null;
  sender_id: number | null;
  sender_name: string | null;
  message_text: string | null;
  caption: string | null;
  has_image: boolean;
  image_description: string | null;
  reply_to_message_id: number | null;
  message_date: number;
  is_question: boolean | null;
  question_confidence: number | null;
}

export interface QAAnalyzerDefaultPrompt {
  prompt_template: string;
  system_prompt: string;
  question_confidence_threshold: number;
}

export interface QAAnalyzerRunRequest {
  group_id: number;
  telegram_message_id: number;
  prompt_template: string;
  system_prompt: string;
  model?: string;
  temperature?: number;
  question_confidence_threshold?: number;
}

export interface QAAnalyzerRunResult {
  raw_response: string;
  parsed: Record<string, any> | null;
  rendered_prompt: string;
  system_prompt: string;
  thread_context: string;
  chain: ChainMessage[];
  question_message_id: number;
  model: string;
  temperature: number | null;
  duration_ms: number;
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

  // GK Knowledge — Message Browser
  gkMessagesBrowser: (params: {
    page?: number;
    page_size?: number;
    group_id?: number | null;
    sender_id?: number | null;
    processed?: boolean | null;
    is_question?: boolean | null;
    analyzed?: boolean | null;
    in_chain?: boolean | null;
    search?: string | null;
    date_from?: string | null;
    date_to?: string | null;
  }) => {
    const searchParams = new URLSearchParams();
    if (params.page) searchParams.set('page', String(params.page));
    if (params.page_size) searchParams.set('page_size', String(params.page_size));
    if (params.group_id != null) searchParams.set('group_id', String(params.group_id));
    if (params.sender_id != null) searchParams.set('sender_id', String(params.sender_id));
    if (params.processed != null) searchParams.set('processed', String(params.processed));
    if (params.is_question != null) searchParams.set('is_question', String(params.is_question));
    if (params.analyzed != null) searchParams.set('analyzed', String(params.analyzed));
    if (params.in_chain != null) searchParams.set('in_chain', String(params.in_chain));
    if (params.search) searchParams.set('search', params.search);
    if (params.date_from) searchParams.set('date_from', params.date_from);
    if (params.date_to) searchParams.set('date_to', params.date_to);
    return request<{ items: GKMessageBrowserItem[]; total: number; page: number; page_size: number }>(
      `/api/gk-knowledge/messages/browser?${searchParams}`,
    );
  },

  gkMessageSenders: (params?: { group_id?: number | null; search?: string | null; limit?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.group_id != null) searchParams.set('group_id', String(params.group_id));
    if (params?.search) searchParams.set('search', params.search);
    if (params?.limit != null) searchParams.set('limit', String(params.limit));
    const query = searchParams.toString();
    return request<GKMessageBrowserSender[]>(`/api/gk-knowledge/messages/senders${query ? `?${query}` : ''}`);
  },

  gkMessageChain: (params: { group_id: number; telegram_message_id: number }) => {
    const searchParams = new URLSearchParams();
    searchParams.set('group_id', String(params.group_id));
    searchParams.set('telegram_message_id', String(params.telegram_message_id));
    return request<{ items: GKMessageChainItem[]; count: number }>(`/api/gk-knowledge/messages/chain?${searchParams}`);
  },

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

  gkResponderSummary: (params?: { group_id?: number | null; date_from?: string | null; date_to?: string | null }) => {
    const searchParams = new URLSearchParams();
    if (params?.group_id != null) searchParams.set('group_id', String(params.group_id));
    if (params?.date_from) searchParams.set('date_from', params.date_from);
    if (params?.date_to) searchParams.set('date_to', params.date_to);
    const query = searchParams.toString();
    return request<GKResponderSummary>(`/api/gk-knowledge/responder/summary${query ? `?${query}` : ''}`);
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

  gkImageUpload: (formData: FormData) =>
    request<{ message: string; queue_id: number; message_id: number; image_path: string }>(
      '/api/gk-knowledge/images/upload',
      {
        method: 'POST',
        body: formData,
      },
    ),

  // GK Knowledge — Image Prompt Tester
  gkImagePromptTesterSupportedModels: () =>
    request<GKSupportedModelsResponse>('/api/gk-knowledge/image-prompt-tester/supported-models'),

  gkImagePromptTesterStats: () =>
    request<GKImagePromptTesterStats>('/api/gk-knowledge/image-prompt-tester/stats'),

  gkImagePrompts: (activeOnly: boolean = true) =>
    request<GKImagePrompt[]>(`/api/gk-knowledge/image-prompt-tester/prompts?active_only=${activeOnly}`),

  gkCreateImagePrompt: (data: { label: string; prompt_text: string; model_name?: string; temperature?: number }) =>
    request<{ id: number; message: string }>('/api/gk-knowledge/image-prompt-tester/prompts', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  gkUpdateImagePrompt: (promptId: number, data: Partial<{ label: string; prompt_text: string; model_name: string; temperature: number }>) =>
    request<{ message: string }>(`/api/gk-knowledge/image-prompt-tester/prompts/${promptId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  gkDeleteImagePrompt: (promptId: number) =>
    request<{ message: string }>(`/api/gk-knowledge/image-prompt-tester/prompts/${promptId}`, {
      method: 'DELETE',
    }),

  gkImageSessions: () =>
    request<GKImagePromptSession[]>('/api/gk-knowledge/image-prompt-tester/sessions'),

  gkCreateImageSession: (data: { name: string; prompt_ids: number[]; image_count?: number; source_group_id?: number; source_date_from?: string; source_date_to?: string }) =>
    request<{ id: number; message: string }>('/api/gk-knowledge/image-prompt-tester/sessions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  gkEstimateImageSession: (data: { prompt_ids: number[]; image_count?: number; source_group_id?: number; source_date_from?: string; source_date_to?: string }) =>
    request<GKImageSessionEstimate>('/api/gk-knowledge/image-prompt-tester/sessions/estimate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  gkGetImageSession: (sessionId: number) =>
    request<GKImagePromptSession>(`/api/gk-knowledge/image-prompt-tester/sessions/${sessionId}`),

  gkGetNextImageComparison: (sessionId: number) =>
    request<GKImageComparison>(`/api/gk-knowledge/image-prompt-tester/sessions/${sessionId}/compare`),

  gkImageVote: (sessionId: number, data: { comparison_id: number; winner: string }) =>
    request<{ message: string }>(`/api/gk-knowledge/image-prompt-tester/sessions/${sessionId}/vote`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  gkImageSessionResults: (sessionId: number) =>
    request<GKSessionResults>(`/api/gk-knowledge/image-prompt-tester/sessions/${sessionId}/results`),

  gkAbandonImageSession: (sessionId: number) =>
    request<{ message: string }>(`/api/gk-knowledge/image-prompt-tester/sessions/${sessionId}/abandon`, {
      method: 'POST',
    }),

  // GK Knowledge — Prompt Tester
  gkPromptTesterSupportedModels: () =>
    request<GKSupportedModelsResponse>('/api/gk-knowledge/prompt-tester/supported-models'),

  gkPromptTesterStats: () =>
    request<GKPromptTesterStats>('/api/gk-knowledge/prompt-tester/stats'),

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

  gkEstimateSession: (data: { prompt_ids: number[]; chains_count?: number; source_group_id?: number; source_date_from?: string; source_date_to?: string }) =>
    request<GKPromptSessionEstimate>('/api/gk-knowledge/prompt-tester/sessions/estimate', {
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

  // GK Knowledge — Final Prompt Tester
  gkFinalPromptTesterSupportedModels: () =>
    request<GKSupportedModelsResponse>('/api/gk-knowledge/final-prompt-tester/supported-models'),

  gkFinalPromptTesterStats: () =>
    request<GKFinalPromptTesterStats>('/api/gk-knowledge/final-prompt-tester/stats'),

  gkFinalPrompts: (activeOnly: boolean = true) =>
    request<GKFinalPrompt[]>(`/api/gk-knowledge/final-prompt-tester/prompts?active_only=${activeOnly}`),

  gkCreateFinalPrompt: (data: { label: string; prompt_template: string; model_name?: string; temperature?: number }) =>
    request<{ id: number; message: string }>('/api/gk-knowledge/final-prompt-tester/prompts', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  gkCloneFinalPrompt: (promptId: number) =>
    request<{ id: number; message: string }>(`/api/gk-knowledge/final-prompt-tester/prompts/${promptId}/clone`, {
      method: 'POST',
    }),

  gkUpdateFinalPrompt: (promptId: number, data: Partial<{ label: string; prompt_template: string; model_name: string; temperature: number }>) =>
    request<{ message: string }>(`/api/gk-knowledge/final-prompt-tester/prompts/${promptId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  gkDeleteFinalPrompt: (promptId: number) =>
    request<{ message: string }>(`/api/gk-knowledge/final-prompt-tester/prompts/${promptId}`, {
      method: 'DELETE',
    }),

  gkPurgeFinalPrompt: (promptId: number) =>
    request<{ message: string }>(`/api/gk-knowledge/final-prompt-tester/prompts/${promptId}/purge`, {
      method: 'DELETE',
    }),

  gkFinalSessions: () =>
    request<GKFinalPromptSession[]>('/api/gk-knowledge/final-prompt-tester/sessions'),

  gkCreateFinalSession: (data: { name: string; prompt_ids: number[]; questions?: string[]; questions_text?: string; source_group_id?: number; judge_mode?: string }) =>
    request<{ id: number; message: string }>('/api/gk-knowledge/final-prompt-tester/sessions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  gkCloneFinalSession: (sessionId: number) =>
    request<{ id: number; message: string }>(`/api/gk-knowledge/final-prompt-tester/sessions/${sessionId}/clone`, {
      method: 'POST',
    }),

  gkStartFinalSession: (sessionId: number) =>
    request<{ id: number; message: string }>(`/api/gk-knowledge/final-prompt-tester/sessions/${sessionId}/start`, {
      method: 'POST',
    }),

  gkUpdateFinalSession: (sessionId: number, data: { name: string; prompt_ids: number[]; questions?: string[]; questions_text?: string; source_group_id?: number }) =>
    request<{ message: string }>(`/api/gk-knowledge/final-prompt-tester/sessions/${sessionId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  gkEstimateFinalSession: (data: { prompt_ids: number[]; questions?: string[]; questions_text?: string }) =>
    request<GKFinalPromptSessionEstimate>('/api/gk-knowledge/final-prompt-tester/sessions/estimate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  gkGetFinalSession: (sessionId: number) =>
    request<GKFinalPromptSession>(`/api/gk-knowledge/final-prompt-tester/sessions/${sessionId}`),

  gkGetNextFinalComparison: (sessionId: number) =>
    request<GKFinalComparison>(`/api/gk-knowledge/final-prompt-tester/sessions/${sessionId}/compare`),

  gkFinalVote: (sessionId: number, data: { comparison_id: number; winner: string }) =>
    request<{ message: string }>(`/api/gk-knowledge/final-prompt-tester/sessions/${sessionId}/vote`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  gkFinalSessionResults: (sessionId: number) =>
    request<GKSessionResults>(`/api/gk-knowledge/final-prompt-tester/sessions/${sessionId}/results`),

  gkAbandonFinalSession: (sessionId: number) =>
    request<{ message: string }>(`/api/gk-knowledge/final-prompt-tester/sessions/${sessionId}/abandon`, {
      method: 'POST',
    }),

  gkDeleteFinalSession: (sessionId: number) =>
    request<{ message: string }>(`/api/gk-knowledge/final-prompt-tester/sessions/${sessionId}`, {
      method: 'DELETE',
    }),

  gkAbandonSession: (sessionId: number) =>
    request<{ message: string }>(`/api/gk-knowledge/prompt-tester/sessions/${sessionId}/abandon`, {
      method: 'POST',
    }),

  gkSessionGenerations: (sessionId: number) =>
    request<Array<{ id: number; prompt_id: number; prompt_label: string; generated_text: string; generated_at: string }>>(`/api/gk-knowledge/prompt-tester/sessions/${sessionId}/generations`),

  // GK Knowledge — Search
  gkSearch: (
    query: string,
    topK: number = 10,
    groupId?: number,
    model?: string,
    image?: File,
    temperature?: number,
  ) => {
    const body = new FormData();
    body.append('query', query);
    body.append('top_k', String(topK));
    if (groupId != null) body.append('group_id', String(groupId));
    if (model) body.append('model', model);
    if (image) body.append('image', image);
    if (typeof temperature === 'number') body.append('temperature', String(temperature));

    return request<GKSearchResponse>(
      '/api/gk-knowledge/search/query',
      {
        method: 'POST',
        body,
      },
    );
  },

  gkSearchSupportedModels: () =>
    request<GKSupportedModelsResponse>('/api/gk-knowledge/search/supported-models'),

  // GK Knowledge — QA Analyzer Sandbox
  gkQAAnalyzerSearch: (query: string, groupId?: number, limit: number = 50) => {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    if (groupId != null) params.set('group_id', String(groupId));
    return request<QAAnalyzerSearchMessage[]>(`/api/gk-knowledge/qa-analyzer-sandbox/search?${params}`);
  },

  gkQAAnalyzerChain: (groupId: number, telegramMessageId: number) =>
    request<ChainMessage[]>(
      `/api/gk-knowledge/qa-analyzer-sandbox/chain?group_id=${groupId}&telegram_message_id=${telegramMessageId}`,
    ),

  gkQAAnalyzerSupportedModels: () =>
    request<GKSupportedModelsResponse>('/api/gk-knowledge/qa-analyzer-sandbox/supported-models'),

  gkQAAnalyzerDefaultPrompt: () =>
    request<QAAnalyzerDefaultPrompt>('/api/gk-knowledge/qa-analyzer-sandbox/default-prompt'),

  gkQAAnalyzerRun: (data: QAAnalyzerRunRequest) =>
    request<QAAnalyzerRunResult>('/api/gk-knowledge/qa-analyzer-sandbox/run', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // GK Knowledge — LLM settings
  gkLLMSettings: () =>
    request<GKLLMSettingsResponse>('/api/gk-knowledge/settings/llm'),

  gkUpdateLLMSettings: (data: GKLLMSettingsUpdateRequest) =>
    request<{ message: string; updated_keys: string[] }>('/api/gk-knowledge/settings/llm', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  // RAG — corpus stats
  gkRAGCorpusStats: () =>
    request<RAGCorpusStatsResponse>('/api/gk-knowledge/rag/corpus-stats'),

  gkRAGDocuments: (params?: {
    page?: number;
    page_size?: number;
    q?: string | null;
    status?: 'active' | 'archived' | 'deleted' | null;
    source_type?: string | null;
    has_summary?: boolean | null;
    sort_by?: 'updated_at' | 'created_at' | 'filename' | 'status' | 'source_type' | 'chunks' | 'chunk_embeddings_ready' | 'summary_embeddings_ready';
    sort_order?: 'asc' | 'desc';
  }) => {
    const search = new URLSearchParams();
    if (params?.page != null) search.set('page', String(params.page));
    if (params?.page_size != null) search.set('page_size', String(params.page_size));
    if (params?.q && params.q.trim()) search.set('q', params.q.trim());
    if (params?.status) search.set('status', params.status);
    if (params?.source_type && params.source_type.trim()) search.set('source_type', params.source_type.trim());
    if (params?.has_summary != null) search.set('has_summary', String(params.has_summary));
    if (params?.sort_by) search.set('sort_by', params.sort_by);
    if (params?.sort_order) search.set('sort_order', params.sort_order);

    const query = search.toString();
    const path = query ? `/api/gk-knowledge/rag/documents?${query}` : '/api/gk-knowledge/rag/documents';
    return request<RAGDocumentsResponse>(path);
  },

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

  /** Получить конфигурацию автозапуска (launch_config.json). */
  pmGetLaunchConfig: () =>
    request<LaunchConfigResponse>('/api/process-manager/launch-config'),

  /** Сохранить конфигурацию автозапуска. */
  pmUpdateLaunchConfig: (config: LaunchConfigPayload) =>
    request<{ success: boolean; message: string }>('/api/process-manager/launch-config', {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  /** Применить конфигурацию автозапуска немедленно. */
  pmApplyLaunchConfig: () =>
    request<{ success: boolean; actions: Record<string, string> }>('/api/process-manager/launch-config/apply', {
      method: 'POST',
    }),

  /** Остановить все процессы и завершить admin_web. */
  pmShutdownAll: () =>
    request<{ success: boolean; stopped: Record<string, string> }>('/api/process-manager/shutdown', {
      method: 'POST',
    }),

  // -----------------------------------------------------------------------
  // GK Terms
  // -----------------------------------------------------------------------

  listTerms: (params: {
    page?: number;
    page_size?: number;
    group_id?: number | null;
    has_definition?: boolean | null;
    status?: string | null;
    min_confidence?: number | null;
    search_text?: string | null;
    expert_status?: string | null;
    sort_by?: string;
    sort_order?: string;
  }) => {
    const sp = new URLSearchParams();
    if (params.page) sp.set('page', String(params.page));
    if (params.page_size) sp.set('page_size', String(params.page_size));
    if (params.group_id != null) sp.set('group_id', String(params.group_id));
    if (params.has_definition != null) sp.set('has_definition', String(params.has_definition));
    if (params.status) sp.set('status', params.status);
    if (params.min_confidence != null) sp.set('min_confidence', String(params.min_confidence));
    if (params.search_text) sp.set('search_text', params.search_text);
    if (params.expert_status) sp.set('expert_status', params.expert_status);
    if (params.sort_by) sp.set('sort_by', params.sort_by);
    if (params.sort_order) sp.set('sort_order', params.sort_order);
    return request<TermListResponse>(`/api/gk-knowledge/terms/list?${sp}`);
  },

  getTermDetail: (termId: number) =>
    request<TermDetail>(`/api/gk-knowledge/terms/${termId}`),

  getTermStats: (groupId?: number) => {
    const p = groupId != null ? `?group_id=${groupId}` : '';
    return request<TermValidationStats>(`/api/gk-knowledge/terms/stats${p}`);
  },

  getTermGroups: () =>
    request<TermGroupInfo[]>('/api/gk-knowledge/terms/groups'),

  validateTerm: (data: {
    term_id: number;
    verdict: string;
    comment?: string;
    edited_term?: string;
    edited_definition?: string;
  }) =>
    request<{ message: string }>('/api/gk-knowledge/terms/validate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getTermHistory: (termId: number) =>
    request<TermValidationHistoryEntry[]>(`/api/gk-knowledge/terms/${termId}/history`),

  getTermUsageMessages: (termId: number, limit = 10) =>
    request<TermUsageMessage[]>(`/api/gk-knowledge/terms/${termId}/usage-messages?limit=${limit}`),

  triggerTermScan: (data: { group_id: number; date_from: string; date_to: string }) =>
    request<{ batch_id: string; message: string }>('/api/gk-knowledge/terms/scan', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getTermScanStatus: (batchId: string) =>
    request<TermScanStatus>(`/api/gk-knowledge/terms/scan/${batchId}/status`),

  triggerTermRecount: (data: { group_id: number }) =>
    request<{ task_id: string; status: string; message: string }>('/api/gk-knowledge/terms/recount', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getTermRecountStatus: (taskId: string) =>
    request<TermRecountStatus>(`/api/gk-knowledge/terms/recount/${taskId}/status`),

  resetTermsData: (data: { confirmation_text: string }) =>
    request<{ message: string; terms_deleted: number; validations_deleted: number; terms_before: number; validations_before: number }>(
      '/api/gk-knowledge/terms/actions/reset',
      {
        method: 'POST',
        body: JSON.stringify(data),
      },
    ),

  addTermManually: (data: { group_id: number; term: string; definition?: string }) =>
    request<{ message: string; term_id: number }>('/api/gk-knowledge/terms/add', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteTerm: (termId: number) =>
    request<{ message: string }>(`/api/gk-knowledge/terms/${termId}`, { method: 'DELETE' }),
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
// Process Manager: Launch Config
// ---------------------------------------------------------------------------

export interface LaunchConfigProcessEntry {
  enabled: boolean;
  flags: string[];
  preset: string | null;
  name: string;
  icon: string;
  category: string;
  description: string;
  available_presets: Array<{
    name: string;
    description: string;
    flags: string[];
    icon: string;
  }>;
  available_flags: Array<{
    name: string;
    flag_type: string;
    description: string;
    default: unknown;
  }>;
}

export interface LaunchConfigResponse {
  description: string;
  processes: Record<string, LaunchConfigProcessEntry>;
}

export interface LaunchConfigPayload {
  description?: string;
  processes: Record<string, {
    enabled: boolean;
    flags: string[];
    preset: string | null;
  }>;
}

// ---------------------------------------------------------------------------
// Process Manager: Groups
// ---------------------------------------------------------------------------

export interface GroupEntry {
  id: number;
  title: string;
  disabled?: boolean;
}

export interface TestTargetGroup {
  id: number;
  title: string;
  participants?: number | null;
}

export interface GKGroupsConfig {
  groups: GroupEntry[];
  test_target_group: TestTargetGroup | null;
  test_target_groups: TestTargetGroup[];
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

  /** GK-группы: переключить disabled-статус. */
  toggleGKGroup: (groupId: number, disabled: boolean) =>
    request<{ groups: GroupEntry[] }>(`/api/process-manager/groups/gk/${groupId}/toggle`, {
      method: 'PATCH',
      body: JSON.stringify({ disabled }),
    }),

  /** GK test target group: установить. */
  setGKTestTarget: (group: TestTargetGroup) =>
    request<{ test_target_group: TestTargetGroup; test_target_groups: TestTargetGroup[] }>('/api/process-manager/groups/gk/test-target', {
      method: 'PUT',
      body: JSON.stringify(group),
    }),

  /** GK test target group: добавить в список выбора. */
  addGKTestTargetOption: (group: TestTargetGroup) =>
    request<{ test_target_groups: TestTargetGroup[] }>('/api/process-manager/groups/gk/test-targets', {
      method: 'POST',
      body: JSON.stringify(group),
    }),

  /** GK test target group: удалить из списка выбора. */
  removeGKTestTargetOption: (groupId: number) =>
    request<{ test_target_groups: TestTargetGroup[]; test_target_group: TestTargetGroup | null }>(`/api/process-manager/groups/gk/test-targets/${groupId}`, {
      method: 'DELETE',
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

  /** Helper-группы: переключить disabled-статус. */
  toggleHelperGroup: (groupId: number, disabled: boolean) =>
    request<{ groups: GroupEntry[] }>(`/api/process-manager/groups/helper/${groupId}/toggle`, {
      method: 'PATCH',
      body: JSON.stringify({ disabled }),
    }),

  /** Собранные группы из БД. */
  getCollectedGroups: () =>
    request<CollectedGroupInfo[]>('/api/process-manager/groups/collected'),

  // -----------------------------------------------------------------------
  // GK Terms
  // -----------------------------------------------------------------------

  listTerms: (params: {
    page?: number;
    page_size?: number;
    group_id?: number | null;
    has_definition?: boolean | null;
    status?: string | null;
    min_confidence?: number | null;
    search_text?: string | null;
    expert_status?: string | null;
    sort_by?: string;
    sort_order?: string;
  }) => {
    const sp = new URLSearchParams();
    if (params.page) sp.set('page', String(params.page));
    if (params.page_size) sp.set('page_size', String(params.page_size));
    if (params.group_id != null) sp.set('group_id', String(params.group_id));
    if (params.has_definition != null) sp.set('has_definition', String(params.has_definition));
    if (params.status) sp.set('status', params.status);
    if (params.min_confidence != null) sp.set('min_confidence', String(params.min_confidence));
    if (params.search_text) sp.set('search_text', params.search_text);
    if (params.expert_status) sp.set('expert_status', params.expert_status);
    if (params.sort_by) sp.set('sort_by', params.sort_by);
    if (params.sort_order) sp.set('sort_order', params.sort_order);
    return request<TermListResponse>(`/api/gk-knowledge/terms/list?${sp}`);
  },

  getTermDetail: (termId: number) =>
    request<TermDetail>(`/api/gk-knowledge/terms/${termId}`),

  getTermStats: (groupId?: number) => {
    const p = groupId != null ? `?group_id=${groupId}` : '';
    return request<TermValidationStats>(`/api/gk-knowledge/terms/stats${p}`);
  },

  getTermGroups: () =>
    request<TermGroupInfo[]>('/api/gk-knowledge/terms/groups'),

  validateTerm: (data: {
    term_id: number;
    verdict: string;
    comment?: string;
    edited_term?: string;
    edited_definition?: string;
  }) =>
    request<{ message: string }>('/api/gk-knowledge/terms/validate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getTermHistory: (termId: number) =>
    request<TermValidationHistoryEntry[]>(`/api/gk-knowledge/terms/${termId}/history`),

  triggerTermScan: (data: { group_id: number; date_from: string; date_to: string }) =>
    request<{ batch_id: string; message: string }>('/api/gk-knowledge/terms/scan', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getTermScanStatus: (batchId: string) =>
    request<TermScanStatus>(`/api/gk-knowledge/terms/scan/${batchId}/status`),

  addTermManually: (data: { group_id: number; term: string; definition?: string }) =>
    request<{ message: string; term_id: number }>('/api/gk-knowledge/terms/add', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteTerm: (termId: number) =>
    request<{ message: string }>(`/api/gk-knowledge/terms/${termId}`, { method: 'DELETE' }),
};
