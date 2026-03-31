const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export async function analyzeUrl(url) {
  if (!import.meta.env.DEV && !API_BASE) {
    throw new Error("The frontend is deployed, but the backend URL is not configured yet. Add VITE_API_BASE_URL in Vercel and redeploy.");
  }

  const response = await fetch(`${API_BASE}/api/v1/analyze`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ url }),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Request failed.");
  }

  return data;
}
