const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

function isSameOriginApiBase(apiBase) {
  if (!apiBase || typeof window === "undefined") {
    return true;
  }

  try {
    return new URL(apiBase, window.location.origin).origin === window.location.origin;
  } catch {
    return false;
  }
}

export function usesSeparateApiOrigin() {
  return Boolean(API_BASE) && !isSameOriginApiBase(API_BASE);
}

export async function analyzeUrl(url) {
  const apiBase = usesSeparateApiOrigin() ? API_BASE : "";

  let response;
  try {
    response = await fetch(`${apiBase}/api/v1/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ url }),
    });
  } catch {
    if (apiBase) {
      throw new Error("Failed to reach the configured backend URL. Remove VITE_API_BASE_URL for same-origin Docker deployments, or update it to the correct backend origin.");
    }
    throw new Error("Failed to reach the application backend on the current origin.");
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.detail || "Request failed.");
  }

  return data;
}
