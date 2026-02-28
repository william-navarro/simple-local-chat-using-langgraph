import type { ChatRequest, StreamEvent, TerminalResult, ProviderInfo, GlobalSettings, ApiKeysState } from "../types"

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000"

export async function* streamChat(
  request: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
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

export async function generateTitle(message: string, provider: string, model: string): Promise<string> {
  try {
    const res = await fetch(`${BASE_URL}/chat/title`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, provider, model }),
    })
    if (!res.ok) return ""
    const data = await res.json()
    return data.title ?? ""
  } catch {
    return ""
  }
}

export async function executeTerminalCommand(
  command: string,
  workingDirectory = ".",
  shell = "cmd",
): Promise<TerminalResult & { status: string; message?: string }> {
  const res = await fetch(`${BASE_URL}/chat/terminal/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command, working_directory: workingDirectory, shell }),
  })
  if (!res.ok) {
    return {
      status: "error",
      command,
      exit_code: -1,
      stdout: "",
      stderr: "",
      truncated: false,
      message: `Backend error: ${res.status}`,
    }
  }
  return res.json()
}

export async function fetchProviders(): Promise<ProviderInfo[]> {
  try {
    const res = await fetch(`${BASE_URL}/providers`)
    if (!res.ok) return []
    return await res.json()
  } catch {
    return []
  }
}

export async function fetchProviderStatus(provider: string): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/providers/${provider}/status`)
    if (!res.ok) return false
    const data = await res.json()
    return data.online === true
  } catch {
    return false
  }
}

export async function fetchProviderModels(provider: string): Promise<string[]> {
  try {
    const res = await fetch(`${BASE_URL}/providers/${provider}/models`)
    if (!res.ok) return []
    const data = await res.json()
    return data.models ?? []
  } catch {
    return []
  }
}

// Backward-compat aliases
export const fetchLMStudioStatus = () => fetchProviderStatus("lm_studio")
export const fetchLMStudioModels = () => fetchProviderModels("lm_studio")

// --- Settings ---

export async function fetchSettings(): Promise<GlobalSettings> {
  const res = await fetch(`${BASE_URL}/settings`)
  if (!res.ok) throw new Error("Failed to fetch settings")
  return res.json()
}

export async function updateSettings(settings: Partial<GlobalSettings>): Promise<GlobalSettings> {
  const res = await fetch(`${BASE_URL}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  })
  if (!res.ok) throw new Error("Failed to update settings")
  return res.json()
}

export async function fetchApiKeys(): Promise<ApiKeysState> {
  const res = await fetch(`${BASE_URL}/settings/keys`)
  if (!res.ok) throw new Error("Failed to fetch API keys")
  return res.json()
}

export async function updateApiKeys(keys: Partial<ApiKeysState>): Promise<void> {
  const res = await fetch(`${BASE_URL}/settings/keys`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(keys),
  })
  if (!res.ok) throw new Error("Failed to update API keys")
}
