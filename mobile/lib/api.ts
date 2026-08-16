export const API_BASE =
  (process.env.EXPO_PUBLIC_API_BASE_URL || 'https://crickanalysis.onrender.com').replace(/\/$/, '');

export function apiUrl(path: string) {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), init);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export type VideoRecord = {
  id: number;
  original_name: string;
  player_name?: string;
  status: string;
  fps?: number;
  duration?: number;
  width?: number;
  height?: number;
  frame_count?: number;
  video_url: string;
  thumbnail_path?: string;
  analysis_mode?: 'quick' | 'shot' | 'full';
  progress_percent?: number;
  progress_stage?: string;
};

export type FrameRecord = {
  id: number;
  timestamp: number;
  frame_number: number;
  image_path: string;
  is_candidate: number;
  kind: string;
};

export type Dashboard = {
  video_count: number;
  completed_count: number;
  player_count: number;
  boundaries: number;
  sixes: number;
  recent: VideoRecord[];
};

export type PlayerRecord = {
  id: number;
  name: string;
  video_count: number;
  completed_analyses?: number;
};
