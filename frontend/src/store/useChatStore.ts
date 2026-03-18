import { create } from "zustand"
import { persist, type PersistStorage, type StorageValue } from "zustand/middleware"
import { v4 as uuidv4 } from "uuid"
import type { Conversation, Message, MessageType, ToolCallInfo, ImageResult, LLMProvider, GlobalSettings, ConversationSettings } from "../types"

/** Wraps localStorage with a throttled setItem to avoid writes on every token. */
function createThrottledStorage<T>(delay = 1000): PersistStorage<T> {
  let timer: ReturnType<typeof setTimeout> | null = null
  let pending: StorageValue<T> | null = null
  let pendingKey: string | null = null

  return {
    getItem: (name) => {
      const raw = localStorage.getItem(name)
      if (!raw) return null
      return JSON.parse(raw) as StorageValue<T>
    },
    setItem: (name, value) => {
      pendingKey = name
      pending = value
      if (!timer) {
        timer = setTimeout(() => {
          timer = null
          if (pending !== null && pendingKey !== null) {
            localStorage.setItem(pendingKey, JSON.stringify(pending))
            pending = null
          }
        }, delay)
      }
    },
    removeItem: (name) => localStorage.removeItem(name),
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const throttledStorage = createThrottledStorage<any>(1000)

export interface PendingTerminalCommand {
  command: string
  workingDirectory: string
  shell: string
}

interface ChatStore {
  conversations: Conversation[]
  activeConversationId: string | null
  isStreaming: boolean
  isThinking: boolean
  isSearching: boolean
  isExecuting: boolean
  isCompressing: boolean
  thinkingMode: boolean
  webSearchMode: boolean
  terminalMode: boolean
  autoApproveTerminal: boolean
  pendingTerminalCommand: PendingTerminalCommand | null
  selectedProvider: LLMProvider
  selectedModel: string
  globalSettings: GlobalSettings
  settingsModalOpen: boolean

  setGlobalSettings: (settings: GlobalSettings) => void
  setSettingsModalOpen: (open: boolean) => void
  setConversationSettings: (conversationId: string, settings: ConversationSettings) => void
  clearConversationSettings: (conversationId: string) => void
  getEffectiveSettings: () => GlobalSettings
  setSelectedProvider: (provider: LLMProvider) => void
  createConversation: () => string
  deleteConversation: (id: string) => void
  setActiveConversation: (id: string) => void
  addMessage: (conversationId: string, message: Omit<Message, "id" | "timestamp">) => string
  appendToken: (conversationId: string, messageId: string, token: string) => void
  setTitle: (conversationId: string, title: string) => void
  setMessageType: (conversationId: string, messageId: string, type: MessageType) => void
  setToolCalls: (conversationId: string, messageId: string, toolCalls: ToolCallInfo[]) => void
  addImage: (conversationId: string, messageId: string, image: ImageResult) => void
  setStreaming: (value: boolean) => void
  setThinking: (value: boolean) => void
  setSearching: (value: boolean) => void
  setExecuting: (value: boolean) => void
  setCompressing: (value: boolean) => void
  setPendingTerminalCommand: (cmd: PendingTerminalCommand | null) => void
  setAutoApproveTerminal: (value: boolean) => void
  toggleThinkingMode: () => void
  toggleWebSearchMode: () => void
  toggleTerminalMode: () => void
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
      isExecuting: false,
      isCompressing: false,
      thinkingMode: false,
      webSearchMode: false,
      terminalMode: false,
      autoApproveTerminal: false,
      pendingTerminalCommand: null,
      selectedProvider: "lm_studio" as LLMProvider,
      selectedModel: "",
      globalSettings: {
        temperature: 0.3,
        top_p: 1.0,
        max_response_tokens: 4096,
        max_history_tokens: 2000,
        system_prompt: "",
        tool_call_max_iterations: 8,
        tool_call_timeout: 120,
      } as GlobalSettings,
      settingsModalOpen: false,

      setGlobalSettings: (settings) => set({ globalSettings: settings }),
      setSettingsModalOpen: (open) => set({ settingsModalOpen: open }),
      setConversationSettings: (conversationId, settings) => {
        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === conversationId ? { ...c, settings } : c
          ),
        }))
      },
      clearConversationSettings: (conversationId) => {
        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === conversationId ? { ...c, settings: undefined } : c
          ),
        }))
      },
      getEffectiveSettings: () => {
        const { globalSettings, conversations, activeConversationId } = get()
        const conv = conversations.find((c) => c.id === activeConversationId)
        if (!conv?.settings) return globalSettings
        return {
          ...globalSettings,
          ...Object.fromEntries(
            Object.entries(conv.settings).filter(([, v]) => v !== undefined)
          ),
        } as GlobalSettings
      },

      createConversation: () => {
        const id = uuidv4()
        const now = Date.now()
        const conversation: Conversation = {
          id,
          title: "New conversation",
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

      addImage: (conversationId, messageId, image) => {
        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === conversationId
              ? {
                  ...c,
                  messages: c.messages.map((m) => {
                    if (m.id !== messageId) return m
                    const existing = m.images ?? []
                    // Deduplicate by file_path
                    if (existing.some((img) => img.file_path === image.file_path)) return m
                    return { ...m, images: [...existing, image] }
                  }),
                }
              : c
          ),
        }))
      },

      setStreaming: (value) => set({ isStreaming: value }),
      setThinking: (value) => set({ isThinking: value }),
      setSearching: (value) => set({ isSearching: value }),
      setExecuting: (value) => set({ isExecuting: value }),
      setCompressing: (value) => set({ isCompressing: value }),
      setPendingTerminalCommand: (cmd) => set({ pendingTerminalCommand: cmd }),
      setAutoApproveTerminal: (value) => set({ autoApproveTerminal: value }),
      toggleThinkingMode: () => set((state) => ({ thinkingMode: !state.thinkingMode })),
      toggleWebSearchMode: () => set((state) => ({ webSearchMode: !state.webSearchMode })),
      toggleTerminalMode: () => set((state) => ({ terminalMode: !state.terminalMode })),
      setSelectedProvider: (provider) => set({ selectedProvider: provider, selectedModel: "" }),
      setSelectedModel: (model) => set({ selectedModel: model }),

      getActiveConversation: () => {
        const { conversations, activeConversationId } = get()
        return conversations.find((c) => c.id === activeConversationId) ?? null
      },
    }),
    {
      name: "langgraph-chat-storage",
      storage: throttledStorage,
      partialize: (state) => ({
        conversations: state.conversations,
        activeConversationId: state.activeConversationId,
        thinkingMode: state.thinkingMode,
        webSearchMode: state.webSearchMode,
        terminalMode: state.terminalMode,
        selectedProvider: state.selectedProvider,
        selectedModel: state.selectedModel,
        globalSettings: state.globalSettings,
      }),
    }
  )
)
