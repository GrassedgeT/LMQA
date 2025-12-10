import { useState, useEffect, useRef } from 'react';
import { conversationAPI } from '../api';
import { handleError } from '../utils';
import MessageContent from '../components/MessageContent';
import './ChatPage.css';

interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  is_edited?: boolean;
  edited_at?: string;
}

interface ChatPageProps {
  currentConversationId: number | null;
  setCurrentConversationId: (id: number | null) => void;
  onConversationChange: () => void;
}

export default function ChatPage({ 
  currentConversationId, 
  setCurrentConversationId,
  onConversationChange 
}: ChatPageProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [useStream, setUseStream] = useState(false);
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null);
  const [streamAbortController, setStreamAbortController] = useState<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);


  // 加载消息 - 只在切换对话时加载，不在发送消息后重新加载
  useEffect(() => {
    if (currentConversationId) {
      // 清理编辑状态
      setEditingMessageId(null);
      // 加载消息
      loadMessages(currentConversationId);
    } else {
      setMessages([]);
      setEditingMessageId(null);
    }
    // 注意：这里不包含loadMessages作为依赖
    // 因为我们只想在currentConversationId变化时触发，而不是在这些函数变化时触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentConversationId]);

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);


  const loadMessages = async (conversationId: number) => {
    try {
      setLoading(true);
      const data = await conversationAPI.getMessages(conversationId);
      if (data && data.messages && Array.isArray(data.messages)) {
        // 确保每条消息都有必需的字段
        const formattedMessages: Message[] = data.messages.map((msg: any) => ({
          id: msg.id,
          role: msg.role as 'user' | 'assistant',
          content: msg.content || '',
          created_at: msg.created_at,
          is_edited: msg.is_edited || false,
          edited_at: msg.edited_at
        }));
        setMessages(formattedMessages);
      } else {
        setMessages([]);
      }
    } catch (err) {
      handleError(err, '加载消息失败');
      setMessages([]);
    } finally {
      setLoading(false);
    }
  };

  const createNewConversation = async () => {
    try {
      const conversation = await conversationAPI.createConversation();
      onConversationChange();
      setCurrentConversationId(conversation.id);
    } catch (err) {
      handleError(err, '创建对话失败');
    }
  };


  const sendMessage = async () => {
    if (!inputValue.trim() || sending) return;
    if (!currentConversationId) {
      const conversation = await conversationAPI.createConversation();
      setCurrentConversationId(conversation.id);
      onConversationChange();
    }

    const userMessage = inputValue.trim();
    setInputValue('');
    setSending(true);

    const tempUserMessage: Message = {
      id: Date.now(),
      role: 'user',
      content: userMessage,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMessage]);

    try {
      if (useStream) {
        // 流式发送
        const abortController = new AbortController();
        setStreamAbortController(abortController);
        
        const tempAssistantMessage: Message = {
          id: Date.now() + 1,
          role: 'assistant',
          content: '',
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, tempAssistantMessage]);

        try {
          await conversationAPI.sendMessageStream(
            currentConversationId!,
            userMessage,
            (token) => {
              if (abortController.signal.aborted) return;
              setMessages((prev) => {
                const updated = [...prev];
                const msgIndex = updated.findIndex((m) => m.id === tempAssistantMessage.id);
                if (msgIndex !== -1) {
                  updated[msgIndex] = {
                    ...updated[msgIndex],
                    content: updated[msgIndex].content + token,
                  };
                }
                return updated;
              });
            },
            async (messageId) => {
              setMessages((prev) => {
                const updated = [...prev];
                const msgIndex = updated.findIndex((m) => m.id === tempAssistantMessage.id);
                if (msgIndex !== -1) {
                  updated[msgIndex] = { ...updated[msgIndex], id: messageId };
                }
                return updated;
              });
              onConversationChange();
              setStreamAbortController(null);
              setSending(false);
              // 不重新加载消息列表，因为流式输出已经实时更新了消息内容
            },
            (error) => {
              setMessages((prev) => prev.filter((m) => m.id !== tempAssistantMessage.id));
              handleError(new Error(error), '发送消息失败');
              setStreamAbortController(null);
              setSending(false);
            },
            abortController.signal
          );
        } catch (err) {
          if (abortController.signal.aborted) {
            setMessages((prev) => prev.filter((m) => m.id !== tempAssistantMessage.id));
          } else {
            handleError(err, '发送消息失败');
          }
          setStreamAbortController(null);
          setSending(false);
        }
      } else {
        // 普通发送
        const response = await conversationAPI.sendMessage(currentConversationId!, userMessage);
        // 确保响应数据结构正确
        if (!response || !response.user_message || !response.assistant_message) {
          throw new Error('服务器返回的数据格式不正确');
        }
        // 更新消息列表，确保包含服务器返回的完整消息
        setMessages((prev) => {
          const filtered = prev.filter((m) => m.id !== tempUserMessage.id);
          // 确保消息对象包含所有必需字段
          const userMsg: Message = {
            id: response.user_message.id,
            role: response.user_message.role as 'user' | 'assistant',
            content: response.user_message.content || '',
            created_at: response.user_message.created_at,
            is_edited: (response.user_message as any).is_edited || false,
            edited_at: (response.user_message as any).edited_at
          };
          const assistantMsg: Message = {
            id: response.assistant_message.id,
            role: response.assistant_message.role as 'user' | 'assistant',
            content: response.assistant_message.content || '',
            created_at: response.assistant_message.created_at,
            is_edited: (response.assistant_message as any).is_edited || false,
            edited_at: (response.assistant_message as any).edited_at
          };
          return [...filtered, userMsg, assistantMsg];
        });
        // 更新对话列表
        onConversationChange();
        // 不重新加载消息列表，因为我们已经用服务器返回的消息更新了状态
        // 这样可以避免覆盖刚刚显示的消息
      }
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== tempUserMessage.id));
      handleError(err, '发送消息失败');
    } finally {
      setSending(false);
    }
  };

  const handleEditMessage = async (messageId: number, newContent: string) => {
    if (!currentConversationId || !newContent.trim()) return;
    try {
      await conversationAPI.updateMessage(currentConversationId, messageId, newContent.trim());
      await loadMessages(currentConversationId);
    } catch (err) {
      handleError(err, '编辑消息失败');
    }
  };

  const handleDeleteMessage = async (messageId: number) => {
    if (!currentConversationId || !confirm('确定要删除这条消息吗？')) return;
    try {
      await conversationAPI.deleteMessage(currentConversationId, messageId);
      await loadMessages(currentConversationId);
    } catch (err) {
      handleError(err, '删除消息失败');
    }
  };

  return (
    <div className="chat-page">
      <div className="chat-main">
        {currentConversationId ? (
          <>
            <div className="chat-header">
              {/* Header content if needed */}
            </div>
            <div className="chat-content">
              <div className="chat-content-main">
                <div className="messages-container">
                  {loading ? (
                    <div className="loading-messages">
                      <div className="loading-spinner"></div>
                      <div>加载中...</div>
                    </div>
                  ) : messages.length === 0 ? (
                    <div className="empty-messages">
                      <div className="empty-icon">💭</div>
                      <div className="empty-text">开始新的对话吧！</div>
                      <div className="empty-hint">输入消息开始与AI助手对话</div>
                    </div>
                  ) : (
                  messages.map((msg) => (
                  <div key={msg.id} className={`message ${msg.role}`}>
                    {editingMessageId === msg.id && msg.role === 'user' ? (
                      <div className="message-edit">
                        <textarea
                          defaultValue={msg.content}
                          onBlur={(e) => {
                            if (e.target.value.trim() && e.target.value !== msg.content) {
                              handleEditMessage(msg.id, e.target.value);
                            }
                            setEditingMessageId(null);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && e.ctrlKey) {
                              e.currentTarget.blur();
                            } else if (e.key === 'Escape') {
                              setEditingMessageId(null);
                            }
                          }}
                          autoFocus
                          rows={3}
                        />
                        <div className="edit-hint">Ctrl+Enter保存，Esc取消</div>
                      </div>
                    ) : (
                      <>
                        {msg.content ? (
                          <MessageContent content={msg.content} />
                        ) : msg.role === 'assistant' ? (
                          <div className="message-loading">
                            <span className="loading-dots">生成中</span>
                          </div>
                        ) : null}
                        {msg.is_edited && (
                          <div className="message-meta">
                            <span className="message-edited">已编辑</span>
                          </div>
                        )}
                        <div className="message-actions">
                          {msg.content && (
                            <button
                              onClick={async () => {
                                try {
                                  await navigator.clipboard.writeText(msg.content);
                                  alert('已复制到剪贴板');
                                } catch (err) {
                                  handleError(err, '复制失败');
                                }
                              }}
                              title="复制"
                            >
                              📋
                            </button>
                          )}
                          {msg.role === 'user' && (
                            <>
                              <button
                                onClick={() => setEditingMessageId(msg.id)}
                                title="编辑"
                              >
                                ✏️
                              </button>
                              <button
                                onClick={() => handleDeleteMessage(msg.id)}
                                title="删除"
                              >
                                🗑️
                              </button>
                            </>
                          )}
                          {msg.role === 'assistant' && (
                            <>
                              <button
                                onClick={async () => {
                                  if (!currentConversationId) return;
                                  const lastUserMessage = messages
                                    .filter(m => m.role === 'user')
                                    .slice(-1)[0];
                                  if (!lastUserMessage) return;
                                  if (!confirm('确定要重新生成回答吗？')) return;
                                  
                                  try {
                                    // 删除最后一条AI消息
                                    const lastAssistantMessage = messages
                                      .filter(m => m.role === 'assistant')
                                      .slice(-1)[0];
                                    if (lastAssistantMessage) {
                                      await conversationAPI.deleteMessage(
                                        currentConversationId,
                                        lastAssistantMessage.id
                                      );
                                    }
                                    
                                    // 重新发送最后一条用户消息
                                    setSending(true);
                                    try {
                                      if (useStream) {
                                        // 流式重新生成
                                        const abortController = new AbortController();
                                        setStreamAbortController(abortController);
                                        
                                        const tempAssistantMessage: Message = {
                                          id: Date.now() + 1,
                                          role: 'assistant',
                                          content: '',
                                          created_at: new Date().toISOString(),
                                        };
                                        setMessages((prev) => [...prev, tempAssistantMessage]);

                                        await conversationAPI.sendMessageStream(
                                          currentConversationId,
                                          lastUserMessage.content,
                                          (token) => {
                                            if (abortController.signal.aborted) return;
                                            setMessages((prev) => {
                                              const updated = [...prev];
                                              const msgIndex = updated.findIndex((m) => m.id === tempAssistantMessage.id);
                                              if (msgIndex !== -1) {
                                                updated[msgIndex] = {
                                                  ...updated[msgIndex],
                                                  content: updated[msgIndex].content + token,
                                                };
                                              }
                                              return updated;
                                            });
                                          },
                                          async (messageId) => {
                                            setMessages((prev) => {
                                              const updated = [...prev];
                                              const msgIndex = updated.findIndex((m) => m.id === tempAssistantMessage.id);
                                              if (msgIndex !== -1) {
                                                updated[msgIndex] = { ...updated[msgIndex], id: messageId };
                                              }
                                              return updated;
                                            });
                                            onConversationChange();
                                            setStreamAbortController(null);
                                            setSending(false);
                                          },
                                          (error) => {
                                            setMessages((prev) => prev.filter((m) => m.id !== tempAssistantMessage.id));
                                            handleError(new Error(error), '重新生成失败');
                                            setStreamAbortController(null);
                                            setSending(false);
                                          },
                                          abortController.signal
                                        );
                                      } else {
                                        // 普通重新生成
                                        const response = await conversationAPI.sendMessage(
                                          currentConversationId,
                                          lastUserMessage.content
                                        );
                                        setMessages((prev) => {
                                          const filtered = prev.filter((m) => m.role !== 'assistant' || m.id !== lastAssistantMessage.id);
                                          return [...filtered, response.user_message, response.assistant_message];
                                        });
                                        onConversationChange();
                                        setSending(false);
                                      }
                                    } catch (err) {
                                      handleError(err, '重新生成失败');
                                      setSending(false);
                                    }
                                  } catch (err) {
                                    handleError(err, '重新生成失败');
                                  }
                                }}
                                title="重新生成"
                              >
                                🔄
                              </button>
                            </>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                ))
                )}
                <div ref={messagesEndRef} />
              </div>
              </div>
            <div className="input-container">
              <div className="input-options">
                <label>
                  <input
                    type="checkbox"
                    checked={useStream}
                    onChange={(e) => setUseStream(e.target.checked)}
                  />
                  <span>流式输出</span>
                </label>
                {sending && streamAbortController && (
                  <button
                    className="stop-btn"
                    onClick={() => {
                      streamAbortController?.abort();
                      setStreamAbortController(null);
                      setSending(false);
                    }}
                  >
                    停止生成
                  </button>
                )}
                {inputValue && (
                  <button
                    className="clear-btn"
                    onClick={() => setInputValue('')}
                    title="清空输入"
                  >
                    清空
                  </button>
                )}
                <span className="char-count">
                  {inputValue.length} / {10000}
                </span>
              </div>
              <div className="input-row">
                <textarea
                  ref={(textarea) => {
                    if (textarea) {
                      textarea.style.height = 'auto';
                      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
                    }
                  }}
                  value={inputValue}
                  onChange={(e) => {
                    setInputValue(e.target.value);
                    // 自动调整高度
                    e.target.style.height = 'auto';
                    e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      sendMessage();
                    }
                  }}
                  placeholder="输入消息... (Shift+Enter换行，Enter发送)"
                  rows={1}
                  style={{ resize: 'none', overflow: 'hidden' }}
                  autoFocus
                />
                <button 
                  onClick={sendMessage} 
                  disabled={sending || !inputValue.trim()}
                  className="send-button"
                >
                  {sending ? (
                    <>
                      <span className="button-icon">⏳</span>
                      <span>发送中...</span>
                    </>
                  ) : (
                    <>
                      <span className="button-icon">➤</span>
                      <span>发送</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
          </>
        ) : (
          <div className="empty-chat">
            <div className="logo-section">
              <div className="logo">LMQA</div>
              <div className="slogan">智能问答助手 · 让知识触手可及</div>
              <div className="subtitle">开始新的对话，探索无限可能</div>
            </div>
            <button onClick={createNewConversation} className="start-chat-btn">
              <span>+</span>
              <span>创建新对话</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}