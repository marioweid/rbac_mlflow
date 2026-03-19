import { auth } from "@/auth";

export async function apiFetch(
  path: string,
  init?: RequestInit
): Promise<Response> {
  const session = await auth();
  const headers = new Headers(init?.headers);

  if (session?.accessToken) {
    headers.set("Authorization", `Bearer ${session.accessToken}`);
  }

  const baseUrl = process.env["API_URL"] ?? "http://api:8000";
  return fetch(`${baseUrl}${path}`, { ...init, headers });
}
