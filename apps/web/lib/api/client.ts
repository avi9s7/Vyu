import { env } from "@/lib/config/env";
import { ApiError } from "@/lib/api/errors";

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers
    },
    credentials: "include"
  });

  if (!response.ok) {
    throw await ApiError.fromResponse(response);
  }

  return response.json() as Promise<T>;
}
