import { createClient } from '@supabase/supabase-js';

const url = import.meta.env.PUBLIC_SUPABASE_URL;
const key = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;

export const supabase = url && key ? createClient(url, key) : null;

// Anonim oturumu yalnızca ilk beğeni tıklanınca açılır (gereksiz anonim kullanıcı oluşmasın).
export async function kullaniciGarantile() {
  if (!supabase) return null;
  const { data: { session } } = await supabase.auth.getSession();
  if (session) return session.user;
  const { data } = await supabase.auth.signInAnonymously();
  return data.user;
}
