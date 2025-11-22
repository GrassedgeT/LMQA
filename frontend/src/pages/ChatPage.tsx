import { useState, useEffect, useRef } from 'react';
import { conversationAPI, memoryAPI } from '../api';
import { handleError } from '../utils';
import MessageContent from '../components/MessageContent';
import './ChatPage.css';

interface Conversation {
  id: number;
  title: string;
  message_count: number;
  last_message_at: string;
  created_at: string;
  updated_at: string;
  last_message_preview?: string;
}

interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  is_edited?: boolean;
  edited_at?: string;
}

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [useStream, setUseStream] = useState(false);
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null);
  const [editingConversationId, setEditingConversationId] = useState<number | null>(null);
  const [selectedConversations, setSelectedConversations] = useState<Set<number>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [streamAbortController, setStreamAbortController] = useState<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 加载对话列表
  useEffect(() => {
    loadConversations();
  }, []);

  // 加载消息
  useEffect(() => {
    if (currentConversationId) {
      loadMessages(currentConversationId);
    } else {
      setMessages([]);
    }
  }, [currentConversationId]);

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadConversations = async () => {
    try {
      const data = await conversationAPI.getConversations();
      setConversations(data.conversations);
      if (data.conversations.length > 0 && !currentConversationId) {
        setCurrentConversationId(data.conversations[0].id);
      }
    } catch (err) {
      handleError(err, '加载对话列表失败');
    }
  };

  const loadMessages = async (conversationId: number) => {
    try {
      setLoading(true);
      const data = await conversationAPI.getMessages(conversationId);
      setMessages(data.messages);
    } catch (err) {
      handleError(err, '加载消息失败');
    } finally {
      setLoading(false);
    }
  };

  const createNewConversation = async () => {
    try {
      const conversation = await conversationAPI.createConversation();
      await loadConversations();
      setCurrentConversationId(conversation.id);
    } catch (err) {
      handleError(err, '创建对话失败');
    }
  };

  const deleteConversation = async (conversationId: number) => {
    if (!confirm('确定要删除这个对话吗？')) return;
    try {
      await conversationAPI.deleteConversation(conversationId);
      if (currentConversationId === conversationId) {
        setCurrentConversationId(null);
      }
      await loadConversations();
    } catch (err) {
      handleError(err, '删除对话失败');
    }
  };

  const sendMessage = async () => {
    if (!inputValue.trim() || sending) return;
    if (!currentConversationId) {
      const conversation = await conversationAPI.createConversation();
      setCurrentConversationId(conversation.id);
      await loadConversations();
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
              await loadConversations();
              setStreamAbortController(null);
            },
            (error) => {
              setMessages((prev) => prev.filter((m) => m.id !== tempAssistantMessage.id));
              handleError(new Error(error), '发送消息失败');
              setStreamAbortController(null);
            },
            abortController.signal
          );
        } catch (err) {
          if (abortController.signal.aborted) {
            setMessages((prev) => prev.filter((m) => m.id !== tempAssistantMessage.id));
          }
          setStreamAbortController(null);
        }
      } else {
        // 普通发送
        const response = await conversationAPI.sendMessage(currentConversationId!, userMessage);
        setMessages((prev) => {
          const filtered = prev.filter((m) => m.id !== tempUserMessage.id);
          return [...filtered, response.user_message, response.assistant_message];
        });
        await loadConversations();
      }
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id === tempUserMessage.id));
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

  const handleEditConversation = async (conversationId: number, newTitle: string) => {
    if (!newTitle.trim()) return;
    try {
      await conversationAPI.updateConversation(conversationId, { title: newTitle.trim() });
      await loadConversations();
      setEditingConversationId(null);
    } catch (err) {
      handleError(err, '重命名对话失败');
    }
  };

  const handleBatchDelete = async () => {
    if (selectedConversations.size === 0) return;
    if (!confirm(`确定要删除选中的 ${selectedConversations.size} 个对话吗？`)) return;
    try {
      await conversationAPI.batchDeleteConversations(Array.from(selectedConversations));
      if (selectedConversations.has(currentConversationId!)) {
        setCurrentConversationId(null);
      }
      setSelectedConversations(new Set());
      await loadConversations();
    } catch (err) {
      handleError(err, '批量删除失败');
    }
  };

  const filteredConversations = conversations.filter(conv =>
    conv.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleExportConversation = async () => {
    if (!currentConversationId || messages.length === 0) {
      alert('没有可导出的对话');
      return;
    }

    try {
      const conversation = conversations.find(c => c.id === currentConversationId);
      const title = conversation?.title || '对话';
      
      // 生成Markdown格式的对话内容
      let markdown = `# ${title}\n\n`;
      markdown += `导出时间: ${new Date().toLocaleString('zh-CN')}\n\n`;
      markdown += '---\n\n';
      
      messages.forEach((msg) => {
        const role = msg.role === 'user' ? '用户' : 'AI助手';
        const time = new Date(msg.created_at).toLocaleString('zh-CN');
        markdown += `## ${role} (${time})\n\n`;
        markdown += `${msg.content}\n\n`;
        markdown += '---\n\n';
      });

      // 创建下载链接
      const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${title}_${new Date().toISOString().split('T')[0]}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
      alert('对话导出成功！');
    } catch (err) {
      handleError(err, '导出失败');
    }
  };

  return (
    <div className="chat-page">
      <div className={`conversation-sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <button
          className="sidebar-toggle"
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          title={sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'}
        >
          {sidebarCollapsed ? '→' : '←'}
        </button>
        {!sidebarCollapsed && (
          <>
            <button className="new-conversation-btn" onClick={createNewConversation}>
              <span style={{ fontSize: '18px' }}>+</span>
              <span>新建对话</span>
            </button>
            <div className="conversation-search">
              <input
                type="text"
                placeholder="搜索对话..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </>
        )}
        {selectedConversations.size > 0 && (
          <div className="batch-actions">
            <span>已选择 {selectedConversations.size} 个</span>
            <button onClick={handleBatchDelete} className="batch-delete-btn">批量删除</button>
            <button onClick={() => setSelectedConversations(new Set())}>取消</button>
          </div>
        )}
        {!sidebarCollapsed && (
          <div className="conversation-list">
            {filteredConversations.map((conv) => (
            <div
              key={conv.id}
              className={`conversation-item ${currentConversationId === conv.id ? 'active' : ''} ${selectedConversations.has(conv.id) ? 'selected' : ''}`}
              onClick={() => {
                if (selectedConversations.size > 0) {
                  const newSelected = new Set(selectedConversations);
                  if (newSelected.has(conv.id)) {
                    newSelected.delete(conv.id);
                  } else {
                    newSelected.add(conv.id);
                  }
                  setSelectedConversations(newSelected);
                } else {
                  setCurrentConversationId(conv.id);
                }
              }}
            >
              {selectedConversations.size > 0 && (
                <input
                  type="checkbox"
                  checked={selectedConversations.has(conv.id)}
                  onChange={(e) => {
                    e.stopPropagation();
                    const newSelected = new Set(selectedConversations);
                    if (e.target.checked) {
                      newSelected.add(conv.id);
                    } else {
                      newSelected.delete(conv.id);
                    }
                    setSelectedConversations(newSelected);
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              )}
              {editingConversationId === conv.id ? (
                <input
                  type="text"
                  defaultValue={conv.title}
                  onBlur={(e) => {
                    if (e.target.value.trim() && e.target.value !== conv.title) {
                      handleEditConversation(conv.id, e.target.value);
                    } else {
                      setEditingConversationId(null);
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.currentTarget.blur();
                    } else if (e.key === 'Escape') {
                      setEditingConversationId(null);
                    }
                  }}
                  autoFocus
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <div className="conversation-info">
                  <div
                    className="conversation-title"
                    onDoubleClick={() => setEditingConversationId(conv.id)}
                  >
                    {conv.title}
                  </div>
                  {conv.last_message_preview && (
                    <div className="conversation-preview">{conv.last_message_preview}</div>
                  )}
                </div>
              )}
              <div className="conversation-actions">
                {selectedConversations.size === 0 && (
                  <>
                    <button
                      className="edit-conv-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingConversationId(conv.id);
                      }}
                      title="重命名"
                    >
                      ✏️
                    </button>
                    <button
                      className="delete-conv-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteConversation(conv.id);
                      }}
                      title="删除"
                    >
                      ×
                    </button>
                  </>
                )}
              </div>
            </div>
            ))}
          </div>
        )}
      </div>
      <div className="chat-main">
        {currentConversationId ? (
          <>
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
                        <MessageContent content={msg.content} />
                        {msg.is_edited && (
                          <div className="message-meta">
                            <span className="message-edited">已编辑</span>
                          </div>
                        )}
                        <div className="message-actions">
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
                                    await conversationAPI.sendMessage(
                                      currentConversationId,
                                      lastUserMessage.content
                                    );
                                    await loadMessages(currentConversationId);
                                  } catch (err) {
                                    handleError(err, '重新生成失败');
                                  }
                                }}
                                title="重新生成"
                              >
                                🔄
                              </button>
                              <button
                                onClick={async () => {
                                  const title = prompt('请输入记忆标题:', msg.content.substring(0, 30));
                                  if (!title || !title.trim()) return;
                                  
                                  try {
                                    await memoryAPI.createMemory({
                                      title: title.trim(),
                                      content: msg.content,
                                      category: 'conversation',
                                      tags: []
                                    });
                                    alert('记忆创建成功！');
                                  } catch (err) {
                                    handleError(err, '创建记忆失败');
                                  }
                                }}
                                title="保存为记忆"
                              >
                                💾
                              </button>
                            </>
                          )}
                          {msg.role === 'user' && (
                            <button
                              onClick={async () => {
                                const title = prompt('请输入记忆标题:', msg.content.substring(0, 30));
                                if (!title || !title.trim()) return;
                                
                                try {
                                  await memoryAPI.createMemory({
                                    title: title.trim(),
                                    content: msg.content,
                                    category: 'conversation',
                                    tags: []
                                  });
                                  alert('记忆创建成功！');
                                } catch (err) {
                                  handleError(err, '创建记忆失败');
                                }
                              }}
                              title="保存为记忆"
                            >
                              💾
                            </button>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
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

