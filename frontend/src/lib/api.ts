import type { ChatRequest, StreamEvent } from "../types"

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000"

export async function* streamChat(request: ChatRequest): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    throw new Error(`Backend error: ${response.status} ${response.statusText}`)
  }

  if (!response.body) {
    throw new Error("No response body")
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() ?? ""

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const raw = line.slice(6).trim()
        if (!raw) continue
        try {
          yield JSON.parse(raw) as StreamEvent
        } catch {
          // malformed chunk, skip
        }
      }
    }
  }
}

export async function generateTitle(message: string, model: string): Promise<string> {
  try {
    const res = await fetch(`${BASE_URL}/chat/title`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, model }),
    })
    if (!res.ok) {
      console.error("[generateTitle] API error:", res.status, await res.text())
      return ""
    }
    const data = await res.json()
    console.log("[generateTitle] Response:", data)
    return data.title ?? ""
  } catch (e) {
    console.error("[generateTitle] Fetch error:", e)
    return ""
  }
}

export async function fetchLMStudioStatus(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/lmstudio/status`)
    if (!res.ok) return false
    const data = await res.json()
    return data.online === true
  } catch {
    return false
  }
}

export async function fetchLMStudioModels(): Promise<string[]> {
  try {
    const res = await fetch(`${BASE_URL}/lmstudio/models`)
    if (!res.ok) return []
    const data = await res.json()
    return data.models ?? []
  } catch {
    return []
  }
}
