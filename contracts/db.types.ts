// Supabase DB 타입 — supabase/migrations/0001~0004 미러 (설계서 §3).
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
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
  };
}
