import { Brain, Globe, Terminal, Tag, Bot, User, Copy, Check } from "lucide-react"
import { useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"
import type { Message, ToolCallInfo } from "../../types"

interface MessageItemProps {
  message: Message
  isStreaming?: boolean
}

const messageTypeLabel: Record<string, string> = {
  simple: "simple",
  summary_request: "summary",
  system_instruction: "instruction",
}

const messageTypeColor: Record<string, string> = {
  simple: "text-zinc-500 bg-zinc-800",
  summary_request: "text-amber-400 bg-amber-900/30",
  system_instruction: "text-violet-400 bg-violet-900/30",
}

// Normalizes models that emit "Reasoning:" / "Answer:" as free text
// Converts to <think>...</think> format that the frontend already handles
function normalizeReasoningFormat(raw: string): string {
  // Already has native tags, skip
  if (/<think(?:ing)?>/.test(raw)) return raw

  // Pattern: **Reasoning:** ... **Answer:** ... (with or without asterisks, case-insensitive)
  const pattern = /^\s*\*{0,2}Reasoning:\*{0,2}\s*([\s\S]*?)\s*\*{0,2}Answer:\*{0,2}\s*([\s\S]*)$/i
  const match = pattern.exec(raw)
  if (match) {
    return `<think>${match[1].trim()}</think>\n${match[2].trim()}`
  }

  return raw
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1 px-2 py-1 rounded text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700 transition-colors duration-150"
      aria-label="Copy code"
    >
      {copied ? <Check size={11} /> : <Copy size={11} />}
      {copied ? "Copied" : "Copy"}
    </button>
  )
}

function CodeBlock({ language, code }: { language: string; code: string }) {
  return (
    <div className="my-2 rounded-lg overflow-hidden border border-zinc-700 max-w-full">
      <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-900 border-b border-zinc-700">
        <span className="text-xs text-zinc-500 font-mono">{language || "text"}</span>
        <CopyButton text={code} />
      </div>
      <div className="overflow-x-auto">
        <SyntaxHighlighter
          language={language || "text"}
          style={vscDarkPlus}
          customStyle={{
            margin: 0,
            padding: "12px 16px",
            background: "#18181b",
            fontSize: "0.8rem",
            lineHeight: "1.5",
          }}
          wrapLongLines={false}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    </div>
  )
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="min-w-0 overflow-hidden">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || "")
            const codeString = String(children).replace(/\n$/, "")
            const isBlock = codeString.includes("\n") || (className ?? "").includes("language-")

            if (isBlock) {
              return <CodeBlock language={match?.[1] ?? ""} code={codeString} />
            }

            return (
              <code
                className="px-1 py-0.5 rounded bg-zinc-700 text-violet-300 text-xs font-mono break-all"
                {...props}
              >
                {children}
              </code>
            )
          },
          p({ children }) {
            return <p className="mb-2 last:mb-0 leading-relaxed break-words">{children}</p>
          },
          strong({ children }) {
            return <strong className="font-semibold text-zinc-100">{children}</strong>
          },
          em({ children }) {
            return <em className="italic text-zinc-300">{children}</em>
          },
          ul({ children }) {
            return <ul className="mb-2 ml-4 space-y-0.5 list-disc marker:text-zinc-500">{children}</ul>
          },
          ol({ children }) {
            return <ol className="mb-2 ml-4 space-y-0.5 list-decimal marker:text-zinc-500">{children}</ol>
          },
          li({ children }) {
            return <li className="leading-relaxed break-words">{children}</li>
          },
          h1({ children }) {
            return <h1 className="text-base font-bold text-zinc-100 mb-2 mt-3 first:mt-0">{children}</h1>
          },
          h2({ children }) {
            return <h2 className="text-sm font-bold text-zinc-100 mb-2 mt-3 first:mt-0">{children}</h2>
          },
          h3({ children }) {
            return <h3 className="text-sm font-semibold text-zinc-200 mb-1.5 mt-2 first:mt-0">{children}</h3>
          },
          blockquote({ children }) {
            return (
              <blockquote className="border-l-2 border-zinc-600 pl-3 my-2 text-zinc-400 italic break-words">
                {children}
              </blockquote>
            )
          },
          a({ href, children }) {
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-violet-400 underline hover:text-violet-300 transition-colors break-all"
              >
                {children}
              </a>
            )
          },
          hr() {
            return <hr className="my-3 border-zinc-700" />
          },
          table({ children }) {
            return (
              <div className="my-2 overflow-x-auto max-w-full">
                <table className="text-xs border-collapse border border-zinc-700">
                  {children}
                </table>
              </div>
            )
          },
          th({ children }) {
            return (
              <th className="px-3 py-1.5 text-left font-semibold text-zinc-200 bg-zinc-800 border border-zinc-700 whitespace-nowrap">
                {children}
              </th>
            )
          },
          td({ children }) {
            return (
              <td className="px-3 py-1.5 text-zinc-300 border border-zinc-700">
                {children}
              </td>
            )
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

function ThinkingBlock({ content, isStreaming }: { content: string; isStreaming: boolean }) {
  return (
    <div className="my-2 rounded-lg bg-indigo-950/40 border border-indigo-800/30 overflow-hidden">
      <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-indigo-800/20">
        <Brain size={11} className={`text-indigo-400 ${isStreaming ? "animate-pulse" : ""}`} />
        <span className={`text-xs font-medium tracking-wide ${isStreaming ? "text-indigo-400 animate-pulse" : "text-indigo-500/70"}`}>
          {isStreaming ? "thinking..." : "reasoning"}
        </span>
        {isStreaming && (
          <span className="flex gap-0.5 ml-0.5">
            <span className="w-1 h-1 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "0ms" }} />
            <span className="w-1 h-1 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "150ms" }} />
            <span className="w-1 h-1 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "300ms" }} />
          </span>
        )}
      </div>
      <div className="px-3 py-2 text-xs text-indigo-300/60 leading-relaxed italic whitespace-pre-wrap break-words">
        {content.trim()}
      </div>
    </div>
  )
}

function SearchBlock({ toolCalls }: { toolCalls: ToolCallInfo[] }) {
  const searchCalls = toolCalls.filter((tc) => tc.name !== "terminal_execute")
  if (searchCalls.length === 0) return null

  return (
    <div className="my-2 rounded-lg bg-blue-950/40 border border-blue-800/30 overflow-hidden">
      <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-blue-800/20">
        <Globe size={11} className="text-blue-400" />
        <span className="text-xs font-medium tracking-wide text-blue-400">
          web search
        </span>
      </div>
      <div className="px-3 py-2 space-y-2">
        {searchCalls.map((tc, i) => (
          <div key={i}>
            <p className="text-xs text-blue-300/80 italic mb-1">
              Searched: &ldquo;{tc.query}&rdquo;
            </p>
            {tc.results && tc.results.length > 0 && (
              <ul className="space-y-1">
                {tc.results.slice(0, 5).map((r, j) => (
                  <li key={j} className="text-xs">
                    <a
                      href={r.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-400 hover:text-blue-300 underline"
                    >
                      {r.title}
                    </a>
                    <span className="text-blue-300/40 ml-1">
                      - {r.snippet.length > 100 ? r.snippet.slice(0, 100) + "..." : r.snippet}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {tc.error && (
              <p className="text-xs text-red-400/70">{tc.error}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function TerminalBlock({ toolCalls }: { toolCalls: ToolCallInfo[] }) {
  const terminalCalls = toolCalls.filter((tc) => tc.name === "terminal_execute")
  if (terminalCalls.length === 0) return null

  return (
    <div className="my-2 rounded-lg bg-green-950/40 border border-green-800/30 overflow-hidden">
      <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-green-800/20">
        <Terminal size={11} className="text-green-400" />
        <span className="text-xs font-medium tracking-wide text-green-400">
          terminal
        </span>
      </div>
      <div className="px-3 py-2 space-y-2">
        {terminalCalls.map((tc, i) => (
          <div key={i}>
            <div className="flex items-center gap-1.5 mb-1">
              <span className="text-xs text-green-300/80 font-mono">
                $ {tc.command}
              </span>
              {tc.terminalResult && (
                <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${
                  tc.terminalResult.exit_code === 0
                    ? "text-green-400 bg-green-900/30"
                    : "text-red-400 bg-red-900/30"
                }`}>
                  exit {tc.terminalResult.exit_code}
                </span>
              )}
            </div>
            {tc.terminalResult?.stdout && (
              <pre className="text-xs text-green-200/60 font-mono bg-zinc-900/50 rounded p-2 overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap">
                {tc.terminalResult.stdout}
              </pre>
            )}
            {tc.terminalResult?.stderr && (
              <pre className="text-xs text-red-400/70 font-mono bg-zinc-900/50 rounded p-2 overflow-x-auto mt-1 whitespace-pre-wrap">
                {tc.terminalResult.stderr}
              </pre>
            )}
            {tc.terminalResult?.truncated && (
              <p className="text-xs text-yellow-500/70 mt-1">Output truncated (exceeded 5000 characters)</p>
            )}
            {tc.error && (
              <p className="text-xs text-red-400/70">{tc.error}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

const CLOSED_THINKING = /<think(?:ing)?>([\s\S]*?)<\/think(?:ing)?>/g
const OPEN_THINKING = /<think(?:ing)?>([^]*)/

interface ContentPart {
  type: "text" | "thinking"
  content: string
  open?: boolean
}

function parseContent(raw: string): ContentPart[] {
  const normalized = normalizeReasoningFormat(raw)
  const parts: ContentPart[] = []
  let lastIndex = 0
  let match

  CLOSED_THINKING.lastIndex = 0
  while ((match = CLOSED_THINKING.exec(normalized)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: "text", content: normalized.slice(lastIndex, match.index) })
    }
    parts.push({ type: "thinking", content: match[1], open: false })
    lastIndex = match.index + match[0].length
  }

  const remaining = normalized.slice(lastIndex)
  const openMatch = OPEN_THINKING.exec(remaining)

  if (openMatch) {
    const before = remaining.slice(0, openMatch.index)
    if (before) parts.push({ type: "text", content: before })
    parts.push({ type: "thinking", content: openMatch[1], open: true })
  } else if (remaining) {
    parts.push({ type: "text", content: remaining })
  }

  return parts
}

export function MessageItem({ message, isStreaming }: MessageItemProps) {
  const isUser = message.role === "user"
  const parts = isUser ? null : parseContent(message.content)

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"} min-w-0`}>
      <div
        className={`
          shrink-0 flex items-center justify-center w-8 h-8 rounded-full
          ${isUser
            ? "bg-gradient-to-br from-violet-600 to-indigo-600"
            : "bg-zinc-800 border border-zinc-700"
          }
        `}
      >
        {isUser
          ? <User size={14} className="text-white" />
          : <Bot size={14} className="text-zinc-300" />
        }
      </div>

      <div className={`flex flex-col gap-1 min-w-0 max-w-[75%] ${isUser ? "items-end" : "items-start"}`}>
        {message.messageType && message.messageType !== "simple" && !isUser && (
          <span
            className={`
              inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium
              ${messageTypeColor[message.messageType] ?? "text-zinc-500 bg-zinc-800"}
            `}
          >
            <Tag size={10} />
            {messageTypeLabel[message.messageType] ?? message.messageType}
          </span>
        )}

        {message.imageBase64 && message.imageMime && (
          <img
            src={`data:${message.imageMime};base64,${message.imageBase64}`}
            alt="attached image"
            className="max-h-48 rounded-xl border border-zinc-700 object-contain mb-1"
          />
        )}

        <div
          className={`
            rounded-2xl text-sm min-w-0 overflow-hidden
            ${isUser
              ? "bg-gradient-to-br from-violet-600 to-indigo-600 text-white rounded-tr-sm px-4 py-2.5 whitespace-pre-wrap leading-relaxed break-words"
              : "bg-zinc-800 text-zinc-100 rounded-tl-sm border border-zinc-700 px-4 py-2.5 w-full"
            }
          `}
        >
          {isUser ? (
            message.content
          ) : (
            <>
              {message.toolCalls && message.toolCalls.length > 0 && (
                <>
                  <SearchBlock toolCalls={message.toolCalls} />
                  <TerminalBlock toolCalls={message.toolCalls} />
                </>
              )}
              {parts?.map((part, i) =>
                part.type === "thinking" ? (
                  <ThinkingBlock
                    key={i}
                    content={part.content}
                    isStreaming={!!isStreaming && !!part.open}
                  />
                ) : (
                  <MarkdownContent key={i} content={part.content} />
                )
              )}
              {isStreaming && (
                <span className="inline-block w-1.5 h-4 bg-zinc-300 ml-0.5 animate-pulse rounded-sm align-middle" />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
