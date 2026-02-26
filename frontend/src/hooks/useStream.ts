import { useCallback } from "react"
import { useChatStore } from "../store/useChatStore"
import { streamChat, generateTitle } from "../lib/api"
import type { MessageRole, ToolCallInfo, SearchResult } from "../types"

export function useStream() {
  const {
    addMessage,
    appendToken,
    setTitle,
    setMessageType,
    setToolCalls,
    setStreaming,
    setThinking,
    setSearching,
    getActiveConversation,
    selectedModel,
    thinkingMode,
    webSearchMode,
  } = useChatStore()

  const sendMessage = useCallback(
    async (content: string, imageBase64?: string, imageMediaType?: string) => {
      const conversation = getActiveConversation()
      if (!conversation) return

      const conversationId = conversation.id
      const isFirstMessage = conversation.messages.length === 0
      const model = selectedModel || "local-model"

      addMessage(conversationId, {
        role: "user" as MessageRole,
        content,
        imageBase64,
        imageMediaType,
      })

      const assistantMessageId = addMessage(conversationId, {
        role: "assistant" as MessageRole,
        content: "",
      })

      setStreaming(true)
      setThinking(true)

      // Generate title FIRST for new conversations — separate endpoint,
      // guarantees it appears before any streaming tokens
      if (isFirstMessage) {
        try {
          console.log("[useStream] Generating title for:", content.slice(0, 50))
          const title = await generateTitle(content, model)
          console.log("[useStream] Title received:", title)
          if (title) setTitle(conversationId, title)
        } catch (e) {
          console.error("[useStream] Title error:", e)
        }
      }

      const historyMessages = conversation.messages.map((m) => ({
        role: m.role,
        content: m.content,
        image_base64: m.imageBase64,
        image_media_type: m.imageMediaType,
      }))

      // Collect tool calls to set on the message after streaming
      const collectedToolCalls: ToolCallInfo[] = []

      try {
        const generator = streamChat({
          thread_id: conversationId,
          messages: historyMessages,
          new_message: content,
          image_base64: imageBase64,
          image_media_type: imageMediaType,
          model,
          thinking_mode: thinkingMode,
          web_search: webSearchMode,
        })

        for await (const event of generator) {
          if (event.type === "thinking_start") {
            setThinking(true)
          } else if (event.type === "tool_start") {
            setThinking(false)
            setSearching(true)
            try {
              const info = JSON.parse(event.content ?? "{}")
              collectedToolCalls.push({
                name: info.name ?? "web_search",
                query: info.args?.query ?? "",
              })
            } catch { /* ignore parse errors */ }
          } else if (event.type === "tool_result") {
            try {
              const result = JSON.parse(event.content ?? "{}")
              // Update the last tool call with results
              const lastTc = collectedToolCalls[collectedToolCalls.length - 1]
              if (lastTc && result.status === "success" && result.results) {
                lastTc.results = result.results as SearchResult[]
              } else if (lastTc && result.status === "error") {
                lastTc.error = result.message
              }
            } catch { /* ignore */ }
            setSearching(false)
            // Persist tool calls on the message
            if (collectedToolCalls.length > 0) {
              setToolCalls(conversationId, assistantMessageId, [...collectedToolCalls])
            }
          } else if (event.type === "tool_error") {
            setSearching(false)
          } else if (event.type === "token") {
            setThinking(false)
            setSearching(false)
            appendToken(conversationId, assistantMessageId, event.content ?? "")
          } else if (event.type === "message_type") {
            setMessageType(
              conversationId,
              assistantMessageId,
              (event.content ?? "simple") as "simple" | "summary_request" | "system_instruction"
            )
          } else if (event.type === "error") {
            setThinking(false)
            setSearching(false)
            appendToken(conversationId, assistantMessageId, `\n\n[Erro: ${event.content}]`)
            break
          } else if (event.type === "done") {
            break
          }
        }
      } catch {
        appendToken(conversationId, assistantMessageId, `\n\n[Erro de conexao com o backend]`)
      } finally {
        setStreaming(false)
        setThinking(false)
        setSearching(false)
      }
    },
    [
      addMessage, appendToken, setTitle, setMessageType, setToolCalls,
      setStreaming, setThinking, setSearching, getActiveConversation,
      selectedModel, thinkingMode, webSearchMode,
    ]
  )

  return { sendMessage }
}
