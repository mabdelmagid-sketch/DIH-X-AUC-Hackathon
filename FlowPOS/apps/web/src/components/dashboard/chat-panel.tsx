"use client";

import { useState, useRef, useEffect } from "react";
import { streamChat, type SSEEvent } from "@/lib/forecasting-api";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui";

interface Message {
  role: "user" | "assistant";
  content: string;
  toolCalls?: string[];
}

const SUGGESTIONS = [
  "What items are low on stock?",
  "What are our top sellers this month?",
  "What should I order this week?",
];

export function ChatPanel() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [currentTools, setCurrentTools] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages, currentTools]);

  async function handleSend(text?: string) {
    const userMsg = (text || input).trim();
    if (!userMsg || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);
    setCurrentTools([]);

    let assistantContent = "";
    const tools: string[] = [];

    try {
      for await (const event of streamChat(userMsg)) {
        switch (event.type) {
          case "tool_call":
            tools.push(event.tool);
            setCurrentTools([...tools]);
            break;
          case "token":
            assistantContent += event.content;
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last?.role === "assistant") {
                last.content = assistantContent;
                last.toolCalls = tools.length > 0 ? tools : undefined;
              } else {
                updated.push({
                  role: "assistant",
                  content: assistantContent,
                  toolCalls: tools.length > 0 ? tools : undefined,
                });
              }
              return updated;
            });
            break;
          case "done":
            break;
          case "error":
            assistantContent = `Error: ${event.message}`;
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: assistantContent },
            ]);
            break;
        }
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Connection error: ${err instanceof Error ? err.message : "Unknown error"}`,
        },
      ]);
    }

    setLoading(false);
    setCurrentTools([]);
  }

  return (
    <>
      {/* Toggle button */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-[var(--primary)] text-white shadow-lg transition-colors hover:opacity-90"
          title="Open AI chat"
        >
          <Icon name="chat" size={24} className="text-white" />
        </button>
      )}

      {/* Chat drawer */}
      <div
        className={cn(
          "fixed top-0 right-0 z-50 flex h-full w-96 flex-col border-s border-[var(--border)] bg-[var(--card)] shadow-xl transition-transform duration-300",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--border)] p-4">
          <div>
            <h2 className="font-brand text-base font-semibold text-[var(--foreground)]">
              FlowPOS AI
            </h2>
            <p className="font-body text-xs text-[var(--muted-foreground)]">
              Ask anything about your inventory
            </p>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="p-1 text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
          >
            <Icon name="close" size={20} />
          </button>
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4">
          {messages.length === 0 && (
            <div className="mt-8 text-center text-[var(--muted-foreground)]">
              <p className="font-body text-sm">Try asking:</p>
              <div className="mt-3 space-y-2">
                {SUGGESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => handleSend(q)}
                    className="block w-full rounded-[var(--radius-m)] bg-[var(--accent)] px-3 py-2 text-start font-body text-xs text-[var(--foreground)] transition-colors hover:bg-[var(--accent)]/80"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              className={cn(
                "max-w-[85%] rounded-xl px-4 py-2.5 font-body text-sm",
                msg.role === "user"
                  ? "ml-auto bg-[var(--primary)] text-white"
                  : "bg-[var(--accent)] text-[var(--foreground)]",
              )}
            >
              {msg.toolCalls && msg.toolCalls.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1">
                  {msg.toolCalls.map((tool, j) => (
                    <span
                      key={j}
                      className="inline-flex items-center rounded-[var(--radius-pill)] bg-[var(--primary)]/15 px-2 py-0.5 font-body text-xs text-[var(--primary)]"
                    >
                      {tool}
                    </span>
                  ))}
                </div>
              )}
              <div className="whitespace-pre-wrap">{msg.content}</div>
            </div>
          ))}

          {/* Loading indicators */}
          {loading &&
            currentTools.length === 0 &&
            messages[messages.length - 1]?.role === "user" && (
              <div className="flex items-center gap-2 font-body text-sm text-[var(--muted-foreground)]">
                <span className="animate-pulse">Thinking...</span>
              </div>
            )}
          {loading &&
            currentTools.length > 0 &&
            !messages.find(
              (m, i) => m.role === "assistant" && i === messages.length - 1,
            ) && (
              <div className="font-body text-xs text-[var(--muted-foreground)]">
                <span className="animate-pulse">Looking up data: </span>
                {currentTools.join(", ")}
              </div>
            )}
        </div>

        {/* Input */}
        <div className="border-t border-[var(--border)] p-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex gap-2"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your inventory..."
              className="flex-1 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--background)] px-3 py-2 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="rounded-[var(--radius-m)] bg-[var(--primary)] px-4 py-2 font-body text-sm text-white transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Send
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
