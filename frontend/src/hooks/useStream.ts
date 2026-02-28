import { useCallback, useRef } from "react"
import { useChatStore } from "../store/useChatStore"
import { streamChat, generateTitle, executeTerminalCommand } from "../lib/api"
import type { MessageRole, ToolCallInfo, SearchResult, TerminalResult, ImageResult } from "../types"

export type TerminalApprovalResult = "approve" | "approve_always" | "deny"

const MAX_TOOL_OUTPUT = 2000
function truncateToolOutput(text: string): string {
  if (text.length <= MAX_TOOL_OUTPUT) return text
  return text.slice(0, MAX_TOOL_OUTPUT) + `\n... (truncated, ${text.length} chars)`
}

export function useStream() {
  const {
    addMessage,
    appendToken,
    setTitle,
    setMessageType,
    setToolCalls,
    addImage,
    setStreaming,
    setThinking,
    setSearching,
    setExecuting,
    setCompressing,
    setPendingTerminalCommand,
    setAutoApproveTerminal,
    getActiveConversation,
    selectedProvider,
    selectedModel,
    thinkingMode,
    webSearchMode,
    terminalMode,
  } = useChatStore()

  // Ref to hold the resolve function for the terminal approval promise
  const approvalResolveRef = useRef<((result: TerminalApprovalResult) => void) | null>(null)

  // AbortController for cancelling the active stream
  const abortRef = useRef<AbortController | null>(null)

  const resolveTerminalApproval = useCallback((result: TerminalApprovalResult) => {
    if (approvalResolveRef.current) {
      approvalResolveRef.current(result)
      approvalResolveRef.current = null
    }
    setPendingTerminalCommand(null)
  }, [setPendingTerminalCommand])

  const waitForApproval = useCallback((command: string, workingDirectory: string, shell = "cmd"): Promise<TerminalApprovalResult> => {
    return new Promise((resolve) => {
      approvalResolveRef.current = resolve
      setPendingTerminalCommand({ command, workingDirectory, shell })
    })
  }, [setPendingTerminalCommand])

  const stopStreaming = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    // Also resolve any pending terminal approval as deny
    if (approvalResolveRef.current) {
      approvalResolveRef.current("deny")
      approvalResolveRef.current = null
    }
    setPendingTerminalCommand(null)
    setStreaming(false)
    setThinking(false)
    setSearching(false)
    setExecuting(false)
    setCompressing(false)
  }, [setPendingTerminalCommand, setStreaming, setThinking, setSearching, setExecuting, setCompressing])

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

      // Create a new AbortController for this stream
      const abortController = new AbortController()
      abortRef.current = abortController

      setStreaming(true)
      setThinking(true)

      // Generate title in background for new conversations (non-blocking)
      if (isFirstMessage) {
        generateTitle(content, selectedProvider || "lm_studio", model)
          .then((title) => { if (title) setTitle(conversationId, title) })
          .catch(() => { /* title generation is non-critical */ })
      }

      const historyMessages = conversation.messages.map((m) => ({
        role: m.role,
        content: m.content,
      }))

      // Collect tool calls to set on the message after streaming
      const collectedToolCalls: ToolCallInfo[] = []
      // Track terminal results for follow-up request
      let terminalToolContext = ""

      try {
        const provider = selectedProvider || "lm_studio"
        const effectiveSettings = useChatStore.getState().getEffectiveSettings()
        const generator = streamChat({
          thread_id: conversationId,
          messages: historyMessages,
          new_message: content,
          image_base64: imageBase64,
          image_media_type: imageMediaType,
          provider,
          model,
          thinking_mode: thinkingMode,
          web_search: webSearchMode,
          terminal_access: terminalMode,
          temperature: effectiveSettings.temperature,
          top_p: effectiveSettings.top_p,
          max_response_tokens: effectiveSettings.max_response_tokens,
          max_history_tokens: effectiveSettings.max_history_tokens,
          system_prompt: effectiveSettings.system_prompt || undefined,
          tool_call_max_iterations: effectiveSettings.tool_call_max_iterations,
        }, abortController.signal)

        for await (const event of generator) {
          if (abortController.signal.aborted) break

          if (event.type === "compressing") {
            setCompressing(true)
          } else if (event.type === "thinking_start") {
            setCompressing(false)
            setThinking(true)
          } else if (event.type === "terminal_pending") {
            setThinking(false)
            setSearching(false)

            try {
              const pending = JSON.parse(event.content ?? "{}")
              const command = pending.command ?? ""
              const workingDirectory = pending.working_directory ?? "."
              const shell = pending.shell ?? "cmd"

              // Check auto-approve
              const autoApprove = useChatStore.getState().autoApproveTerminal
              let decision: TerminalApprovalResult

              if (autoApprove) {
                decision = "approve"
              } else {
                // Show dialog and wait for user decision
                decision = await waitForApproval(command, workingDirectory, shell)
              }

              if (abortController.signal.aborted) break

              if (decision === "approve_always") {
                setAutoApproveTerminal(true)
              }

              if (decision === "approve" || decision === "approve_always") {
                // Execute the command
                setExecuting(true)
                const result = await executeTerminalCommand(command, workingDirectory, shell)
                setExecuting(false)

                if (abortController.signal.aborted) break

                const tcInfo: ToolCallInfo = {
                  name: "terminal_execute",
                  query: "",
                  command,
                  shell,
                }

                if (result.status === "success") {
                  tcInfo.terminalResult = {
                    command: result.command,
                    exit_code: result.exit_code ?? 0,
                    stdout: result.stdout ?? "",
                    stderr: result.stderr ?? "",
                    truncated: result.truncated ?? false,
                  }
                  const truncated = truncateToolOutput(JSON.stringify(result))
                  terminalToolContext += `\n\n[terminal_execute("${command}")]\n${truncated}`
                } else {
                  tcInfo.error = result.message ?? "Execution failed"
                  terminalToolContext += `\n\n[terminal_execute("${command}")]\nError: ${result.message ?? "failed"}`
                }

                collectedToolCalls.push(tcInfo)
                setToolCalls(conversationId, assistantMessageId, [...collectedToolCalls])
              } else {
                // User denied
                const tcInfo: ToolCallInfo = {
                  name: "terminal_execute",
                  query: "",
                  command,
                  shell,
                  error: "Command rejected by user",
                }
                collectedToolCalls.push(tcInfo)
                setToolCalls(conversationId, assistantMessageId, [...collectedToolCalls])
                terminalToolContext += `\n\n[terminal_execute("${command}")]\nDenied by user.`
              }
            } catch {
              setExecuting(false)
            }
          } else if (event.type === "tool_start") {
            setThinking(false)
            try {
              const info = JSON.parse(event.content ?? "{}")
              if (info.name === "terminal_execute") {
                setExecuting(true)
                collectedToolCalls.push({
                  name: "terminal_execute",
                  query: "",
                  command: info.args?.command ?? "",
                })
              } else {
                setSearching(true)
                collectedToolCalls.push({
                  name: info.name ?? "web_search",
                  query: info.args?.query ?? "",
                })
              }
            } catch { /* ignore parse errors */ }
          } else if (event.type === "tool_result") {
            try {
              const result = JSON.parse(event.content ?? "{}")
              const lastTc = collectedToolCalls[collectedToolCalls.length - 1]
              if (lastTc?.name === "terminal_execute") {
                if (result.status === "success") {
                  lastTc.terminalResult = {
                    command: result.command,
                    exit_code: result.exit_code,
                    stdout: result.stdout,
                    stderr: result.stderr,
                    truncated: result.truncated,
                  } as TerminalResult
                } else {
                  lastTc.error = result.message
                }
              } else if (lastTc) {
                if (result.status === "success" && result.results) {
                  lastTc.results = result.results as SearchResult[]
                } else if (result.status === "error") {
                  lastTc.error = result.message
                }
              }
            } catch { /* ignore */ }
            setSearching(false)
            setExecuting(false)
            // Persist tool calls on the message
            if (collectedToolCalls.length > 0) {
              setToolCalls(conversationId, assistantMessageId, [...collectedToolCalls])
            }
          } else if (event.type === "image_result") {
            try {
              const imgData = JSON.parse(event.content ?? "{}") as ImageResult
              addImage(conversationId, assistantMessageId, imgData)
            } catch { /* ignore */ }
          } else if (event.type === "tool_error") {
            setSearching(false)
            setExecuting(false)
          } else if (event.type === "token") {
            setThinking(false)
            setSearching(false)
            setExecuting(false)
            setCompressing(false)
            appendToken(conversationId, assistantMessageId, event.content ?? "")
          } else if (event.type === "message_type") {
            setCompressing(false)
            setMessageType(
              conversationId,
              assistantMessageId,
              (event.content ?? "simple") as "simple" | "summary_request" | "system_instruction"
            )
          } else if (event.type === "error") {
            setThinking(false)
            setSearching(false)
            setExecuting(false)
            setCompressing(false)
            appendToken(conversationId, assistantMessageId, `\n\n[Error: ${event.content}]`)
            break
          } else if (event.type === "done") {
            break
          }
        }

        // If terminal commands were executed (via approval), make a follow-up
        // streaming request so the model can generate a response based on results
        if (terminalToolContext && !abortController.signal.aborted) {
          const followUpAbort = new AbortController()
          abortRef.current = followUpAbort

          const followUpGenerator = streamChat({
            thread_id: conversationId,
            messages: [
              ...historyMessages,
              { role: "user" as MessageRole, content },
            ],
            new_message: `[Tool results:${terminalToolContext}]\n\n${content}`,
            provider,
            model,
            thinking_mode: thinkingMode,
            web_search: webSearchMode,
            terminal_access: terminalMode,
          }, followUpAbort.signal)

          for await (const event of followUpGenerator) {
            if (followUpAbort.signal.aborted) break

            if (event.type === "token") {
              setThinking(false)
              setSearching(false)
              setExecuting(false)
              appendToken(conversationId, assistantMessageId, event.content ?? "")
            } else if (event.type === "thinking_start") {
              setThinking(true)
            } else if (event.type === "tool_start") {
              setThinking(false)
              try {
                const info = JSON.parse(event.content ?? "{}")
                if (info.name === "terminal_execute") {
                  setExecuting(true)
                } else {
                  setSearching(true)
                }
                collectedToolCalls.push({
                  name: info.name ?? "unknown",
                  query: info.args?.query ?? "",
                  command: info.args?.command ?? "",
                })
              } catch { /* ignore */ }
            } else if (event.type === "tool_result") {
              try {
                const result = JSON.parse(event.content ?? "{}")
                const lastTc = collectedToolCalls[collectedToolCalls.length - 1]
                if (lastTc?.name === "terminal_execute") {
                  if (result.status === "success") {
                    lastTc.terminalResult = {
                      command: result.command,
                      exit_code: result.exit_code,
                      stdout: result.stdout,
                      stderr: result.stderr,
                      truncated: result.truncated,
                    } as TerminalResult
                  } else {
                    lastTc.error = result.message
                  }
                } else if (lastTc) {
                  if (result.status === "success" && result.results) {
                    lastTc.results = result.results as SearchResult[]
                  } else if (result.status === "error") {
                    lastTc.error = result.message
                  }
                }
              } catch { /* ignore */ }
              setSearching(false)
              setExecuting(false)
              if (collectedToolCalls.length > 0) {
                setToolCalls(conversationId, assistantMessageId, [...collectedToolCalls])
              }
            } else if (event.type === "image_result") {
              try {
                const imgData = JSON.parse(event.content ?? "{}") as ImageResult
                addImage(conversationId, assistantMessageId, imgData)
              } catch { /* ignore */ }
            } else if (event.type === "tool_error") {
              setSearching(false)
              setExecuting(false)
            } else if (event.type === "error") {
              setThinking(false)
              setSearching(false)
              setExecuting(false)
              appendToken(conversationId, assistantMessageId, `\n\n[Error: ${event.content}]`)
              break
            } else if (event.type === "done") {
              break
            }
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // Stream was cancelled by user — not an error
        } else {
          appendToken(conversationId, assistantMessageId, `\n\n[Backend connection error]`)
        }
      } finally {
        abortRef.current = null
        setStreaming(false)
        setThinking(false)
        setSearching(false)
        setExecuting(false)
        setCompressing(false)
        setPendingTerminalCommand(null)
      }
    },
    [
      addMessage, appendToken, setTitle, setMessageType, setToolCalls, addImage,
      setStreaming, setThinking, setSearching, setExecuting, setCompressing, getActiveConversation,
      setPendingTerminalCommand, setAutoApproveTerminal, waitForApproval,
      selectedProvider, selectedModel, thinkingMode, webSearchMode, terminalMode,
    ]
  )

  return { sendMessage, stopStreaming, resolveTerminalApproval }
}
