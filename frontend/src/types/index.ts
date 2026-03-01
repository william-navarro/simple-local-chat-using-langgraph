export type LLMProvider = "lm_studio" | "ollama" | "openai" | "anthropic" | "google" | "cli_proxy"

export interface ProviderInfo {
  id: LLMProvider
  name: string
  available: boolean
}

export type MessageRole = "user" | "assistant" | "system"

export type MessageType = "simple" | "summary_request" | "system_instruction"

export interface SearchResult {
  position: number
  title: string
  url: string
  snippet: string
}

export interface TerminalResult {
  command: string
  exit_code: number
  stdout: string
  stderr: string
  truncated: boolean
}

export interface ImageResult {
  file_path: string
  media_type: string
  base64: string
}

export interface ToolCallInfo {
  name: string
  query: string
  command?: string
  shell?: string
  results?: SearchResult[]
  terminalResult?: TerminalResult
  imageResult?: ImageResult
  error?: string
}

export interface Message {
  id: string
  role: MessageRole
  content: string
  messageType?: MessageType
  imageBase64?: string
  imageMediaType?: string
  toolCalls?: ToolCallInfo[]
  images?: ImageResult[]
  timestamp: number
}

export interface ConversationSettings {
  temperature?: number
  top_p?: number
  max_response_tokens?: number
  max_history_tokens?: number
  system_prompt?: string
  tool_call_max_iterations?: number
}

export interface Conversation {
  id: string
  title: string
  messages: Message[]
  settings?: ConversationSettings
  createdAt: number
  updatedAt: number
}

export interface StreamEvent {
  type:
    | "token"
    | "title"
    | "message_type"
    | "thinking_start"
    | "thinking_end"
    | "done"
    | "error"
    | "tool_start"
    | "tool_result"
    | "tool_error"
    | "terminal_pending"
    | "image_result"
    | "compressing"
  content?: string
}

export interface ChatRequest {
  thread_id: string
  messages: {
    role: MessageRole
    content: string
    image_base64?: string
    image_media_type?: string
  }[]
  new_message: string
  image_base64?: string
  image_media_type?: string
  provider: string
  model: string
  thinking_mode: boolean
  web_search: boolean
  terminal_access: boolean
  temperature?: number
  top_p?: number
  max_response_tokens?: number
  max_history_tokens?: number
  system_prompt?: string
  tool_call_max_iterations?: number
}

export interface GlobalSettings {
  temperature: number
  top_p: number
  max_response_tokens: number
  max_history_tokens: number
  system_prompt: string
  tool_call_max_iterations: number
  tool_call_timeout: number
}

export interface ApiKeysState {
  openai_api_key: string
  anthropic_api_key: string
  google_api_key: string
}

export interface ProviderUrlsState {
  lm_studio_url: string
  ollama_url: string
  cli_proxy_url: string
}
