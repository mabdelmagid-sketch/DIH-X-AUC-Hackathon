import { createClient, type SupabaseClient as BaseClient } from "@supabase/supabase-js";
import type { Database } from "@pos/db";

export type SupabaseClient = BaseClient<Database>;

export async function createDb(accessToken?: string): Promise<SupabaseClient> {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

  const options: Record<string, unknown> = {};

  // If we have an access token, pass it as the auth header so the client is authenticated
  if (accessToken) {
    options.global = {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    };
  }

  return createClient<Database>(supabaseUrl, supabaseAnonKey, options);
}

export function createAdminDb(): SupabaseClient {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

  return createClient<Database>(supabaseUrl, supabaseServiceKey);
}
