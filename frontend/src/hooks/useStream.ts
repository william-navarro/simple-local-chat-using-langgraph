import { useCallback, useRef } from "react"
import { useChatStore } from "../store/useChatStore"
import { streamChat, resumeGraph, generateTitle, executeTerminalCommand } from "../lib/api"
import type { MessageRole, ToolCallInfo, SearchResult, TerminalResult, ImageResult } from "../types"

export type TerminalApprovalResult = "approve" | "approve_always" | "deny"

/** Batches rapid appendToken calls into ~30fps flushes to avoid per-token re-renders. */
function createTokenBuffer(appendToken: (cid: string, mid: string, t: string) => void) {
  let buffer = ""
  let cid = ""
  let mid = ""
  let raf = 0

  function flush() {
    raf = 0
    if (buffer) {
      appendToken(cid, mid, buffer)
      buffer = ""
    }
  }

  return {
    push(conversationId: string, messageId: string, token: string) {
      cid = conversationId
      mid = messageId
      buffer += token
      if (!raf) raf = requestAnimationFrame(flush)
    },
    flush() {
      if (raf) { cancelAnimationFrame(raf); raf = 0 }
      flush()
    },
  }
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

  const tokenBufferRef = useRef(createTokenBuffer(appendToken))

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

      // Collect tool calls to set on the message after streaming
      const collectedToolCalls: ToolCallInfo[] = []

      try {
        const provider = selectedProvider || "lm_studio"
        const effectiveSettings = useChatStore.getState().getEffectiveSettings()
        const generator = streamChat({
          conversation_id: conversationId,
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
          } else if (event.type === "terminal_interrupt" || event.type === "terminal_pending") {
            setThinking(false)
            setSearching(false)
            setExecuting(false)

            try {
              const pending = JSON.parse(event.content ?? "{}")
              const command = pending.command ?? ""
              const workingDirectory = pending.working_directory ?? "."
              const shell = pending.shell ?? "cmd"
              // graph_thread_id is sent by backend for resume (unique per request)
              const graphThreadId = pending.graph_thread_id ?? conversationId

              // Check auto-approve
              const autoApprove = useChatStore.getState().autoApproveTerminal
              let decision: TerminalApprovalResult

              if (autoApprove) {
                decision = "approve"
              } else {
                decision = await waitForApproval(command, workingDirectory, shell)
              }

              if (abortController.signal.aborted) break

              if (decision === "approve_always") {
                setAutoApproveTerminal(true)
              }

              const approved = decision === "approve" || decision === "approve_always"
              let execResult: Record<string, unknown> | undefined

              if (approved) {
                // Execute the command locally and pass result to graph resume
                setExecuting(true)
                const result = await executeTerminalCommand(command, workingDirectory, shell)
                setExecuting(false)

                if (abortController.signal.aborted) break

                execResult = result as unknown as Record<string, unknown>

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
                } else {
                  tcInfo.error = result.message ?? "Execution failed"
                }

                collectedToolCalls.push(tcInfo)
                setToolCalls(conversationId, assistantMessageId, [...collectedToolCalls])
              } else {
                const tcInfo: ToolCallInfo = {
                  name: "terminal_execute",
                  query: "",
                  command,
                  shell,
                  error: "Command rejected by user",
                }
                collectedToolCalls.push(tcInfo)
                setToolCalls(conversationId, assistantMessageId, [...collectedToolCalls])
              }

              // Resume the graph and handle chained terminal interrupts
              let currentGraphThreadId = graphThreadId
              let currentApproved = approved
              let currentExecResult = execResult

              // Loop to handle chained terminal commands (LLM may request multiple)
              // eslint-disable-next-line no-constant-condition
              while (true) {
                const resumeAbort = new AbortController()
                abortRef.current = resumeAbort

                const resumeProvider = selectedProvider || "lm_studio"
                const resumeGenerator = resumeGraph(
                  currentGraphThreadId,
                  currentApproved,
                  currentExecResult,
                  resumeProvider,
                  model,
                  resumeAbort.signal,
                )

                let gotNestedInterrupt = false

                for await (const resumeEvent of resumeGenerator) {
                  if (resumeAbort.signal.aborted) break

                  if (resumeEvent.type === "terminal_interrupt") {
                    // Another terminal command — handle it in the next iteration
                    setThinking(false)
                    setSearching(false)
                    setExecuting(false)

                    try {
                      const nestedPending = JSON.parse(resumeEvent.content ?? "{}")
                      const nestedCommand = nestedPending.command ?? ""
                      const nestedWd = nestedPending.working_directory ?? "."
                      const nestedShell = nestedPending.shell ?? "cmd"
                      currentGraphThreadId = nestedPending.graph_thread_id ?? currentGraphThreadId

                      const nestedAutoApprove = useChatStore.getState().autoApproveTerminal
                      let nestedDecision: TerminalApprovalResult
                      if (nestedAutoApprove) {
                        nestedDecision = "approve"
                      } else {
                        nestedDecision = await waitForApproval(nestedCommand, nestedWd, nestedShell)
                      }

                      if (resumeAbort.signal.aborted) break

                      if (nestedDecision === "approve_always") {
                        setAutoApproveTerminal(true)
                      }

                      currentApproved = nestedDecision === "approve" || nestedDecision === "approve_always"
                      currentExecResult = undefined

                      if (currentApproved) {
                        setExecuting(true)
                        const nestedResult = await executeTerminalCommand(nestedCommand, nestedWd, nestedShell)
                        setExecuting(false)

                        if (resumeAbort.signal.aborted) break

                        currentExecResult = nestedResult as unknown as Record<string, unknown>

                        const nestedTcInfo: ToolCallInfo = {
                          name: "terminal_execute",
                          query: "",
                          command: nestedCommand,
                          shell: nestedShell,
                        }
                        if (nestedResult.status === "success") {
                          nestedTcInfo.terminalResult = {
                            command: nestedResult.command,
                            exit_code: nestedResult.exit_code ?? 0,
                            stdout: nestedResult.stdout ?? "",
                            stderr: nestedResult.stderr ?? "",
                            truncated: nestedResult.truncated ?? false,
                          }
                        } else {
                          nestedTcInfo.error = nestedResult.message ?? "Execution failed"
                        }
                        collectedToolCalls.push(nestedTcInfo)
                        setToolCalls(conversationId, assistantMessageId, [...collectedToolCalls])
                      } else {
                        collectedToolCalls.push({
                          name: "terminal_execute",
                          query: "",
                          command: nestedCommand,
                          shell: nestedShell,
                          error: "Command rejected by user",
                        })
                        setToolCalls(conversationId, assistantMessageId, [...collectedToolCalls])
                      }

                      gotNestedInterrupt = true
                    } catch {
                      setExecuting(false)
                    }
                    break  // break inner for-loop to resume again in while-loop
                  } else if (resumeEvent.type === "token") {
                    setThinking(false)
                    setSearching(false)
                    setExecuting(false)
                    tokenBufferRef.current.push(conversationId, assistantMessageId, resumeEvent.content ?? "")
                  } else if (resumeEvent.type === "thinking_start") {
                    setThinking(true)
                  } else if (resumeEvent.type === "tool_start") {
                    setThinking(false)
                    try {
                      const info = JSON.parse(resumeEvent.content ?? "{}")
                      if (info.name === "terminal_execute") {
                        // Don't add to collectedToolCalls — the nested terminal_interrupt
                        // handler will add the entry with proper result data
                        setExecuting(true)
                      } else {
                        setSearching(true)
                        collectedToolCalls.push({
                          name: info.name ?? "unknown",
                          query: info.args?.query ?? "",
                          command: info.args?.command ?? "",
                        })
                      }
                    } catch { /* ignore */ }
                  } else if (resumeEvent.type === "tool_result") {
                    try {
                      const result = JSON.parse(resumeEvent.content ?? "{}")
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
                  } else if (resumeEvent.type === "image_result") {
                    try {
                      const imgData = JSON.parse(resumeEvent.content ?? "{}") as ImageResult
                      addImage(conversationId, assistantMessageId, imgData)
                    } catch { /* ignore */ }
                  } else if (resumeEvent.type === "message_type") {
                    setMessageType(
                      conversationId,
                      assistantMessageId,
                      (resumeEvent.content ?? "simple") as "simple" | "summary_request" | "system_instruction"
                    )
                  } else if (resumeEvent.type === "error") {
                    setThinking(false)
                    setSearching(false)
                    setExecuting(false)
                    tokenBufferRef.current.flush()
                    appendToken(conversationId, assistantMessageId, `\n\n[Error: ${resumeEvent.content}]`)
                    break
                  } else if (resumeEvent.type === "done") {
                    break
                  }
                }

                // If no nested interrupt, we're done with the resume chain
                if (!gotNestedInterrupt || resumeAbort.signal.aborted) break
              }
            } catch {
              setExecuting(false)
            }
          } else if (event.type === "tool_start") {
            setThinking(false)
            try {
              const info = JSON.parse(event.content ?? "{}")
              if (info.name === "terminal_execute") {
                // Don't add to collectedToolCalls here — the terminal_interrupt
                // handler will add the entry with proper result data
                setExecuting(true)
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
            tokenBufferRef.current.push(conversationId, assistantMessageId, event.content ?? "")
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
            tokenBufferRef.current.flush()
            appendToken(conversationId, assistantMessageId, `\n\n[Error: ${event.content}]`)
            break
          } else if (event.type === "done") {
            break
          }
        }

      } catch (err) {
        tokenBufferRef.current.flush()
        if (err instanceof DOMException && err.name === "AbortError") {
          // Stream was cancelled by user — not an error
        } else {
          appendToken(conversationId, assistantMessageId, `\n\n[Backend connection error]`)
        }
      } finally {
        tokenBufferRef.current.flush()
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
