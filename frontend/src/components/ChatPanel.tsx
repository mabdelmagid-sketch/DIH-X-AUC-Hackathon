"use client";

import { useState, useRef, useEffect } from "react";
import { streamChat, type SSEEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Message {
  role: "user" | "assistant";
  content: string;
  toolCalls?: string[];
}

export default function ChatPanel() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [currentTools, setCurrentTools] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages, currentTools]);

  async function handleSend() {
    if (!input.trim() || loading) return;

    const userMsg = input.trim();
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
          className="fixed bottom-6 right-6 w-14 h-14 bg-brand-600 text-white rounded-full shadow-lg flex items-center justify-center hover:bg-brand-700 transition-colors z-50"
          title="Open chat"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        </button>
      )}

      {/* Chat drawer */}
      <div
        className={cn(
          "fixed top-0 right-0 h-full w-96 bg-white border-l border-gray-200 shadow-xl flex flex-col z-50 transition-transform duration-300",
          open ? "translate-x-0" : "translate-x-full"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <div>
            <h2 className="font-semibold text-gray-900">FlowCast Chat</h2>
            <p className="text-xs text-gray-500">Ask anything about your inventory</p>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="p-1 text-gray-400 hover:text-gray-600"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-gray-400 mt-8">
              <p className="text-sm">Try asking:</p>
              <div className="mt-3 space-y-2">
                {[
                  "What items are low on stock?",
                  "What are our top sellers this month?",
                  "What should I order this week?",
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => {
                      setInput(q);
                    }}
                    className="block w-full text-left text-xs px-3 py-2 rounded-lg bg-gray-50 hover:bg-gray-100 text-gray-600 transition-colors"
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
                "max-w-[85%] rounded-xl px-4 py-2.5 text-sm",
                msg.role === "user"
                  ? "ml-auto bg-brand-600 text-white"
                  : "bg-gray-100 text-gray-800"
              )}
            >
              {msg.toolCalls && msg.toolCalls.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-2">
                  {msg.toolCalls.map((tool, j) => (
                    <span
                      key={j}
                      className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-blue-100 text-blue-700"
                    >
                      {tool}
                    </span>
                  ))}
                </div>
              )}
              <div className="prose whitespace-pre-wrap">{msg.content}</div>
            </div>
          ))}

          {/* Loading indicator */}
          {loading && currentTools.length === 0 && messages[messages.length - 1]?.role === "user" && (
            <div className="flex items-center gap-2 text-gray-400 text-sm">
              <span className="animate-pulse">Thinking...</span>
            </div>
          )}
          {loading && currentTools.length > 0 && !messages.find((m, i) => m.role === "assistant" && i === messages.length - 1) && (
            <div className="text-xs text-gray-500">
              <span className="animate-pulse">Looking up data: </span>
              {currentTools.join(", ")}
            </div>
          )}
        </div>

        {/* Input */}
        <div className="p-4 border-t border-gray-200">
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
              className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Send
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
