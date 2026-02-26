import { create } from "zustand"
import { persist } from "zustand/middleware"
import { v4 as uuidv4 } from "uuid"
import type { Conversation, Message, MessageType, ToolCallInfo } from "../types"

interface ChatStore {
  conversations: Conversation[]
  activeConversationId: string | null
  isStreaming: boolean
  isThinking: boolean
  isSearching: boolean
  thinkingMode: boolean
  webSearchMode: boolean
  selectedModel: string

  createConversation: () => string
  deleteConversation: (id: string) => void
  setActiveConversation: (id: string) => void
  addMessage: (conversationId: string, message: Omit<Message, "id" | "timestamp">) => string
  appendToken: (conversationId: string, messageId: string, token: string) => void
  setTitle: (conversationId: string, title: string) => void
  setMessageType: (conversationId: string, messageId: string, type: MessageType) => void
  setToolCalls: (conversationId: string, messageId: string, toolCalls: ToolCallInfo[]) => void
  setStreaming: (value: boolean) => void
  setThinking: (value: boolean) => void
  setSearching: (value: boolean) => void
  toggleThinkingMode: () => void
  toggleWebSearchMode: () => void
  setSelectedModel: (model: string) => void
  getActiveConversation: () => Conversation | null
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      conversations: [],
      activeConversationId: null,
      isStreaming: false,
      isThinking: false,
      isSearching: false,
      thinkingMode: false,
      webSearchMode: false,
      selectedModel: "",

      createConversation: () => {
        const id = uuidv4()
        const now = Date.now()
        const conversation: Conversation = {
          id,
          title: "Nova conversa",
          messages: [],
          createdAt: now,
          updatedAt: now,
        }
        set((state) => ({
          conversations: [conversation, ...state.conversations],
          activeConversationId: id,
        }))
        return id
      },

      deleteConversation: (id) => {
        set((state) => {
          const remaining = state.conversations.filter((c) => c.id !== id)
          const newActive =
            state.activeConversationId === id
              ? remaining[0]?.id ?? null
              : state.activeConversationId
          return { conversations: remaining, activeConversationId: newActive }
        })
      },

      setActiveConversation: (id) => set({ activeConversationId: id }),

      addMessage: (conversationId, message) => {
        const id = uuidv4()
        const now = Date.now()
        const newMessage: Message = { ...message, id, timestamp: now }
        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === conversationId
              ? { ...c, messages: [...c.messages, newMessage], updatedAt: now }
              : c
          ),
        }))
        return id
      },

      appendToken: (conversationId, messageId, token) => {
        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === conversationId
              ? {
                  ...c,
                  messages: c.messages.map((m) =>
                    m.id === messageId ? { ...m, content: m.content + token } : m
                  ),
                }
              : c
          ),
        }))
      },

      setTitle: (conversationId, title) => {
        // Sanitize: strip any leaked <think> tags, take first line, limit length
        const clean = title
          .replace(/<think>[\s\S]*?<\/think>/gi, "")
          .replace(/<think>[\s\S]*/gi, "")
          .replace(/<[^>]*>/g, "")
          .split("\n")[0]
          .trim()
          .slice(0, 80)
        if (!clean) return
        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === conversationId ? { ...c, title: clean } : c
          ),
        }))
      },

      setMessageType: (conversationId, messageId, type) => {
        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === conversationId
              ? {
                  ...c,
                  messages: c.messages.map((m) =>
                    m.id === messageId ? { ...m, messageType: type } : m
                  ),
                }
              : c
          ),
        }))
      },

      setToolCalls: (conversationId, messageId, toolCalls) => {
        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === conversationId
              ? {
                  ...c,
                  messages: c.messages.map((m) =>
                    m.id === messageId ? { ...m, toolCalls } : m
                  ),
                }
              : c
          ),
        }))
      },

      setStreaming: (value) => set({ isStreaming: value }),
      setThinking: (value) => set({ isThinking: value }),
      setSearching: (value) => set({ isSearching: value }),
      toggleThinkingMode: () => set((state) => ({ thinkingMode: !state.thinkingMode })),
      toggleWebSearchMode: () => set((state) => ({ webSearchMode: !state.webSearchMode })),
      setSelectedModel: (model) => set({ selectedModel: model }),

      getActiveConversation: () => {
        const { conversations, activeConversationId } = get()
        return conversations.find((c) => c.id === activeConversationId) ?? null
      },
    }),
    { name: "langgraph-chat-storage" }
  )
)
