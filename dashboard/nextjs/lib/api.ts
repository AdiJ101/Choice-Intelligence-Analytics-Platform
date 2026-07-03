// lib/api.ts — Typed fetch wrappers for all FastAPI endpoints
// All calls route through Next.js proxy (/api/*) → http://localhost:8000/api/*

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`${BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
    });
  }
  const res = await fetch(url.toString(), { next: { revalidate: 0 } });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body?: object): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
  return res.json();
}

// ── Types ────────────────────────────────────────────────────────────────────
export interface Overview {
  total_posts: number;
  total_comments: number;
  total_likes: number;
  total_views: number;
}

export interface Category {
  category_id: number;
  category_name: string;
}

export interface Post {
  post_id: number;
  title: string;
  url: string;
  post_type: string;
  publish_timestamp: string;
  category_name: string;
  platform_display_name: string;
  handle_display_name: string;
  latest_likes: number;
  latest_views: number;
  latest_comments: number;
  latest_shares: number;
  total_engagement: number;
}

export interface PostDetail {
  post_id: number;
  title: string;
  url: string;
  post_type: string;
  publish_timestamp: string;
  category_name: string;
  platform_display_name: string;
  handle_display_name: string;
  // These may be absent on the detail endpoint — derive from engagement_history if needed
  latest_likes?: number;
  latest_views?: number;
  latest_comments?: number;
  body: string;
  comments: Comment[];
  engagement_history: EngagementSnapshot[];
}

export interface Comment {
  comment_id: number;
  author: string;
  text: string;
  timestamp: string;
  likes: number;
}

export interface EngagementSnapshot {
  snapshot_timestamp: string;
  likes_count: number;
  views_count: number;
  comments_count: number;
}

export interface TopPost {
  post_id: number;
  title: string;
  url: string;
  post_type: string;
  publish_timestamp: string;
  category_name: string;
  platform_display_name: string;
  total_engagement: number;
}

export interface CategoryAnalytics {
  category_name: string;
  post_count: number;
  total_likes: number;
  total_views: number;
  total_comments: number;
  total_engagement: number;
}

export interface ScraperStatus {
  status: string;
  last_successful_scrape: string | null;
  next_scheduled_scrape: string | null;
  scraped_today?: number;
  recent_videos?: any[];
  message?: string;
}

export interface AIJob {
  job_id: string;
  status: string;
  progress: number;
  message?: string;
  started_at?: string;
  completed_at?: string;
}

export interface AIAnalyticsResult {
  job_id: string;
  status: string;
  created_at: string;
  customer_intelligence?: {
    trending_topics: string[];
    sentiment_summary: string;
    common_questions: string[];
    pain_points: string[];
  };
  company_intelligence?: {
    key_messages: string[];
    content_themes: string[];
    brand_positioning: string;
  };
  summary?: string;
}

// ── API calls ────────────────────────────────────────────────────────────────
export const api = {
  overview: () => get<Overview>('/api/overview'),

  categories: () =>
    get<{ data: Category[] }>('/api/categories').then(r => r.data),

  posts: (params?: {
    category?: string;
    platform?: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
    offset?: number;
  }) => get<{ data: Post[]; total: number }>('/api/posts', params as never),

  postDetail: (id: number) =>
    get<PostDetail>(`/api/posts/${id}`),

  topPosts: (params?: {
    limit?: number;
    category?: string;
    date_from?: string;
    date_to?: string;
  }) => get<{ data: TopPost[] }>('/api/top-posts', params as never),

  byCategory: () =>
    get<{ data: CategoryAnalytics[] }>('/api/analytics/by-category').then(r => r.data),

  engagementTrend: (params?: {
    category?: string;
    date_from?: string;
    date_to?: string;
  }) => get<{ data: unknown[] }>('/api/analytics/engagement-trend', params as never),

  scraperStatus: () =>
    get<ScraperStatus>('/api/scraper/status'),

  scraperControl: (command: string) =>
    post<{ message: string }>('/api/scraper/control', { command }),

  startAIJob: (params?: {
    category?: string;
    date_from?: string;
    date_to?: string;
  }) => post<AIJob>('/api/ai-analytics/job', params),

  getAIJobStatus: (jobId: string) =>
    get<AIJob>(`/api/ai-analytics/job/${jobId}`),

  getLastAIAnalytics: () =>
    get<AIAnalyticsResult>('/api/ai-analytics/last'),

  getActiveAIJob: () =>
    get<AIJob | null>('/api/ai-analytics/active-job'),

  clearAIAnalytics: () =>
    post<{ message: string }>('/api/ai-analytics/clear'),

  askAI: (question: string, history?: { role: string; content: string }[]) =>
    post<{ answer: string; sources?: unknown[] }>('/api/ask', { question, top_k: 8, history }),
};
