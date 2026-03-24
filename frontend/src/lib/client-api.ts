"use client";

export function clientApiFetch(
  path: string,
  accessToken: string | undefined,
  init?: RequestInit,
): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  return fetch(`/api${path}`, { ...init, headers });
}
