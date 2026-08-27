// Supabase 클라이언트. 번들에 들어가는 값은 VITE_ 접두 2개뿐이다 (설계서 §8).
// service key 와 DB URL 은 절대 여기에 오지 않는다 — worker 전용이다.
import { createClient, type SupabaseClient } from '@supabase/supabase-js';

import type { Database } from '../../../contracts/db.types';

const url = import.meta.env.VITE_SUPABASE_URL;
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

export const missingEnv: string[] = [
  url ? null : 'VITE_SUPABASE_URL',
  publishableKey ? null : 'VITE_SUPABASE_PUBLISHABLE_KEY',
].filter((name): name is string => name !== null);

export const supabase: SupabaseClient<Database> | null =
  missingEnv.length === 0 ? createClient<Database>(url!, publishableKey!) : null;
