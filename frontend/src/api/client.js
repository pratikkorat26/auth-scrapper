const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export async function analyzeUrl(url) {
  const apiBase = API_BASE || "";
  const response = await fetch(`${apiBase}/api/v1/analyze`, {
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
