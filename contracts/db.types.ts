// Supabase DB 타입 — supabase/migrations/0001~0006 미러 (설계서 §3).
// SQL 이 정본이다. 스키마를 바꾸면 이 파일도 같이 고친다.

export type Json = string | number | boolean | null | { [key: string]: Json } | Json[];

export interface Database {
  public: {
    Tables: {
      projects: {
        Row: {
          id: string;
          slug: string;
          name: string;
          structure: string | null;
          coord_system: Json;
          coord_assumptions: string[];
          created_at: string;
        };
        Insert: {
          id?: string;
          slug: string;
          name: string;
          structure?: string | null;
          coord_system: Json;
          coord_assumptions?: string[];
          created_at?: string;
        };
        Update: Partial<Database['public']['Tables']['projects']['Insert']>;
      };
      sheets: {
        Row: {
          id: string;
          project_id: string;
          ord: string;
          drawing_no_from_filename: string;
          drawing_no_from_content: string | null;
          title_from_filename: string;
          title_from_content: string | null;
          scale_from_content: string | null;
          grade: '핵심' | '참고';
          catalog_status: 'unverified' | 'match' | 'mismatch' | 'unreadable';
          page_count: number;
          created_at: string;
        };
        Insert: {
          id?: string;
          project_id: string;
          ord: string;
          drawing_no_from_filename: string;
          drawing_no_from_content?: string | null;
          title_from_filename: string;
          title_from_content?: string | null;
          scale_from_content?: string | null;
          grade: '핵심' | '참고';
          catalog_status?: 'unverified' | 'match' | 'mismatch' | 'unreadable';
          page_count: number;
          created_at?: string;
        };
        Update: Partial<Database['public']['Tables']['sheets']['Insert']>;
      };
      sheet_pages: {
        Row: {
          id: string;
          sheet_id: string;
          page_no: number;
          width_px: number | null;
          height_px: number | null;
          created_at: string;
        };
        Insert: {
          id?: string;
          sheet_id: string;
          page_no: number;
          width_px?: number | null;
          height_px?: number | null;
          created_at?: string;
        };
        Update: Partial<Database['public']['Tables']['sheet_pages']['Insert']>;
      };
      assets: {
        Row: {
          id: string;
          project_id: string;
          sheet_id: string | null;
          sheet_page_id: string | null;
          kind: 'dxf' | 'pdf' | 'png' | 'photo';
          role: 'source' | 'derived';
          rel_path: string;
          bytes: number;
          sha256: string;
          storage_path: string | null;
          created_at: string;
        };
        Insert: {
          id?: string;
          project_id: string;
          sheet_id?: string | null;
          sheet_page_id?: string | null;
          kind: 'dxf' | 'pdf' | 'png' | 'photo';
          role: 'source' | 'derived';
          rel_path: string;
          bytes: number;
          sha256: string;
          storage_path?: string | null;
          created_at?: string;
        };
        Update: Partial<Database['public']['Tables']['assets']['Insert']>;
      };
      readings: {
        Row: {
          id: string;
          project_id: string;
          region: string;
          item: string;
          value_raw: string;
          unit: string | null;
          basis_sheet_id: string;
          basis_page_id: string | null;
          basis_mm_bbox: Json;
          crosscheck: Json | null;
          status: '확정' | '추정' | '검토지적';
          round: number;
          created_at: string;
        };
        Insert: never;
        Update: never;
      };
      ambiguities: {
        Row: {
          id: string;
          project_id: string;
          item: string;
          basis_sheet_id: string;
          sheet_page_id: string | null;
          mm_bbox: Json;
          options: Json;
          model_impact: string;
          crop_rel_path: string | null;
          status: '대기' | '결정' | '잠정';
          created_at: string;
        };
        Insert: never;
        Update: never;
      };
      decisions: {
        Row: {
          id: string;
          project_id: string;
          ambiguity_id: string;
          choice_index: number;
          choice_label: string;
          provisional: boolean;
          note: string;
          decided_by: string;
          decided_at: string;
        };
        Insert: {
          id?: string;
          project_id: string;
          ambiguity_id: string;
          choice_index: number;
          choice_label: string;
          provisional?: boolean;
          note?: string;
          decided_by?: string;
          decided_at?: string;
        };
        Update: never;
      };
      builds: {
        Row: {
          id: string; project_id: string; version: number; kind: 'pilot' | 'full' | 'agent'; segment: string;
          content_sha256: string; glb_path: string; files: BuildFiles; stats: BuildStats;
          status: '대기' | '승인' | '반려'; git_sha: string | null; created_at: string;
        };
        Insert: never;
        Update: never;
      };
      build_sections: {
        Row: {
          id: string; build_id: string; section_key: string; code: string; label: string; glb_path: string;
          bytes: number; sha256: string; meshes: number; triangles: number; selfcheck: SectionSelfcheck;
          status: '대기' | '승인' | '반려'; source: 'builder' | 'agent';
        };
        Insert: never;
        Update: never;
      };
      approvals: {
        Row: {
          id: string; project_id: string; build_id: string; section_id: string | null; user_id: string;
          verdict: '승인' | '반려'; note: string; created_at: string;
        };
        Insert: {
          id?: string; project_id: string; build_id: string; section_id?: string | null; user_id?: string;
          verdict: '승인' | '반려'; note?: string; created_at?: string;
        };
        Update: never;
      };
      jobs: {
        Row: {
          id: string; project_id: string; kind: 'model-section'; section_key: string; request: string;
          parent_job_id: string | null; status: 'queued' | 'running' | 'done' | 'failed'; attempts: number;
          cost_usd: number; budget_usd: number; result: JobResult | null; build_id: string | null; user_id: string;
          created_at: string; updated_at: string;
        };
        Insert: {
          id?: string; project_id: string; kind: 'model-section'; section_key: string; request?: string;
          parent_job_id?: string | null; budget_usd?: number; user_id?: string;
        };
        Update: never;
      };
      job_events: {
        Row: { id: number; job_id: string; ts: string; level: 'info' | 'warn' | 'error'; message: string };
        Insert: never;
        Update: never;
      };
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
  };
}

// ── M4 보조 타입 (builds.files / builds.stats / build_sections.selfcheck 의 jsonb 형식) ──
export interface BuildFiles { renders: string[]; json: string[]; views: string | null; agent?: string[] }
export interface BuildStats {
  meshes: number; triangles: number;
  selfcheck: { pass: number; fail: number; skipped: number };
  measure: { pass: number; fail: number; info: number } | null;
  compare: { match: number; mismatch: number; na: number } | null;
  agent?: AgentScoreSummary | null;
}
export interface SectionSelfcheck {
  pass: number; fail: number;
  checks: Array<{ label: string; ok: boolean | null; detail: string; group: string }>;
}

// ── M5 보조 타입 (builds.stats.agent / jobs.result 의 jsonb 형식) ──
export interface AgentScoreSummary {
  pass: boolean; only_ours: number; only_ref: number; bbox_dev_max_m: number | null;
  section_fail: number; assembled_fail: number; measure_fail: number | null; attempts: number;
}
export interface JobResult {
  pass: boolean; reason?: string; attempts: number; cost_usd: number; build_version?: number; build_id?: string;
  assumptions?: string[]; questions?: string[]; score?: AgentScoreSummary; error?: string;
}
