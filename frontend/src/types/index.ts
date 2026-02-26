export type MessageRole = "user" | "assistant" | "system"

export type MessageType = "simple" | "summary_request" | "system_instruction"

export interface SearchResult {
  position: number
  title: string
  url: string
  snippet: string
}

export interface ToolCallInfo {
  name: string
  query: string
  results?: SearchResult[]
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
  timestamp: number
}

export interface Conversation {
  id: string
  title: string
  messages: Message[]
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
  model: string
  thinking_mode: boolean
  web_search: boolean
}
