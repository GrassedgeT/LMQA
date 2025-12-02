import { useState, useEffect, useRef } from 'react';
import { conversationAPI, memoryAPI } from '../api';
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

interface Memory {
  id: number;
  conversation_id?: number;
  title: string;
  content: string;
  category?: string;
  tags?: string;
  memory_type?: string;
  created_at: string;
  updated_at: string;
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
  const [conversationMemories, setConversationMemories] = useState<Memory[]>([]);
  const [showMemoryPanel, setShowMemoryPanel] = useState(false);
  const [editingMemoryId, setEditingMemoryId] = useState<number | null>(null);
  const [showAddMemoryForm, setShowAddMemoryForm] = useState(false);
  const [newMemoryTitle, setNewMemoryTitle] = useState('');
  const [newMemoryContent, setNewMemoryContent] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);


  // 加载消息 - 只在切换对话时加载，不在发送消息后重新加载
  useEffect(() => {
    if (currentConversationId) {
      // 清理编辑状态
      setEditingMessageId(null);
      setEditingMemoryId(null);
      // 加载消息和记忆
      loadMessages(currentConversationId);
      loadConversationMemories(currentConversationId);
    } else {
      setMessages([]);
      setConversationMemories([]);
      setEditingMessageId(null);
      setEditingMemoryId(null);
    }
    // 注意：这里不包含loadMessages和loadConversationMemories作为依赖
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

  const loadConversationMemories = async (conversationId: number) => {
    try {
      const data = await memoryAPI.getMemories(conversationId, 1, 50);
      setConversationMemories(data.memories);
    } catch (err) {
      handleError(err, '加载对话记忆失败');
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


  const handleCreateMemory = async (title: string, content: string) => {
    if (!currentConversationId || !title.trim() || !content.trim()) {
      alert('标题和内容不能为空');
      return;
    }

    // 验证长度
    if (title.trim().length > 200) {
      alert('标题长度不能超过200个字符');
      return;
    }

    if (content.trim().length > 10000) {
      alert('内容长度不能超过10000个字符');
      return;
    }

    try {
      // 格式化内容：去除首尾空白，规范化换行
      const formattedContent = content
        .trim()
        .replace(/\r\n/g, '\n')
        .replace(/\r/g, '\n');

      await memoryAPI.createMemory({
        title: title.trim(),
        content: formattedContent,
        category: 'conversation',
        tags: [],
        conversation_id: currentConversationId
      });
      await loadConversationMemories(currentConversationId);
      setNewMemoryTitle('');
      setNewMemoryContent('');
      setShowAddMemoryForm(false);
      alert('记忆创建成功！');
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '创建记忆失败';
      if (errorMessage.includes('非JSON格式')) {
        alert('服务器响应格式错误，请稍后重试或联系管理员');
      } else {
        handleError(err, '创建记忆失败');
      }
    }
  };

  const handleUpdateMemory = async (memoryId: number, title: string, content: string) => {
    if (!title.trim() || !content.trim()) {
      alert('标题和内容不能为空');
      return;
    }

    // 验证长度
    if (title.trim().length > 200) {
      alert('标题长度不能超过200个字符');
      return;
    }

    if (content.trim().length > 10000) {
      alert('内容长度不能超过10000个字符');
      return;
    }

    try {
      // 格式化内容：去除首尾空白，规范化换行
      const formattedContent = content
        .trim()
        .replace(/\r\n/g, '\n')
        .replace(/\r/g, '\n');

      await memoryAPI.updateMemory(memoryId, {
        title: title.trim(),
        content: formattedContent
      });
      if (currentConversationId) {
        await loadConversationMemories(currentConversationId);
      }
      setEditingMemoryId(null);
      alert('记忆更新成功！');
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '更新记忆失败';
      if (errorMessage.includes('非JSON格式')) {
        alert('服务器响应格式错误，请稍后重试或联系管理员');
      } else {
        handleError(err, '更新记忆失败');
      }
    }
  };

  const handleDeleteMemory = async (memoryId: number) => {
    if (!confirm('确定要删除这条记忆吗？')) return;
    try {
      await memoryAPI.deleteMemory(memoryId);
      if (currentConversationId) {
        await loadConversationMemories(currentConversationId);
      }
      alert('记忆删除成功！');
    } catch (err) {
      handleError(err, '删除记忆失败');
    }
  };

  return (
    <div className="chat-page">
      <div className="chat-main">
        {currentConversationId ? (
          <>
            <div className="chat-header">
              <div className="chat-header-actions">
                <button
                  className={`memory-panel-toggle ${showMemoryPanel ? 'active' : ''}`}
                  onClick={() => setShowMemoryPanel(!showMemoryPanel)}
                  title={showMemoryPanel ? '隐藏记忆面板' : '显示记忆面板'}
                >
                  🧠 {showMemoryPanel ? '隐藏记忆' : '显示记忆'} ({conversationMemories.length})
                </button>
              </div>
            </div>
            <div className="chat-content">
              <div className="chat-content-main">
                <div className={`messages-container ${showMemoryPanel ? 'with-memory-panel' : ''}`}>
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
                              {msg.content && (
                                <button
                                  onClick={async () => {
                                    if (!currentConversationId) {
                                      alert('请先选择一个对话');
                                      return;
                                    }

                                    // 自动生成标题：取内容前50个字符，去除换行和多余空格
                                    const autoTitle = msg.content
                                      .replace(/\n/g, ' ')
                                      .replace(/\s+/g, ' ')
                                      .trim()
                                      .substring(0, 50);
                                    
                                    const title = prompt('请输入记忆标题:', autoTitle || '新记忆');
                                    if (!title || !title.trim()) return;

                                    try {
                                      // 格式化内容：确保内容规范
                                      const formattedContent = msg.content.trim();
                                      
                                      // 验证内容长度
                                      if (formattedContent.length === 0) {
                                        alert('内容不能为空');
                                        return;
                                      }

                                      if (formattedContent.length > 10000) {
                                        alert('内容过长，请选择较短的内容保存');
                                        return;
                                      }

                                      await memoryAPI.createMemory({
                                        title: title.trim(),
                                        content: formattedContent,
                                        category: 'conversation',
                                        tags: [],
                                        conversation_id: currentConversationId
                                      });
                                      // 刷新记忆列表
                                      if (currentConversationId) {
                                        await loadConversationMemories(currentConversationId);
                                      }
                                      alert('记忆创建成功！');
                                    } catch (err) {
                                      const errorMessage = err instanceof Error ? err.message : '创建记忆失败';
                                      if (errorMessage.includes('非JSON格式')) {
                                        alert('服务器响应格式错误，请稍后重试或联系管理员');
                                      } else {
                                        handleError(err, '创建记忆失败');
                                      }
                                    }
                                  }}
                                  title="保存为记忆"
                                >
                                  💾
                                </button>
                              )}
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
              {showMemoryPanel && (
                <div className="memory-panel">
                  <div className="memory-panel-header">
                    <h3>对话记忆 ({conversationMemories.length})</h3>
                    <div className="memory-panel-header-actions">
                      <button
                        className="memory-add-btn"
                        onClick={() => {
                          setShowAddMemoryForm(!showAddMemoryForm);
                          if (showAddMemoryForm) {
                            setNewMemoryTitle('');
                            setNewMemoryContent('');
                          }
                        }}
                        title="添加记忆"
                      >
                        {showAddMemoryForm ? '取消' : '+'}
                      </button>
                      <button
                        className="memory-panel-close"
                        onClick={() => setShowMemoryPanel(false)}
                        title="关闭记忆面板"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                  <div className="memory-list">
                    {showAddMemoryForm && (
                      <div className="memory-item memory-add-form">
                        <div className="memory-edit">
                          <input
                            type="text"
                            value={newMemoryTitle}
                            onChange={(e) => setNewMemoryTitle(e.target.value)}
                            placeholder="记忆标题"
                            className="memory-edit-title"
                          />
                          <textarea
                            value={newMemoryContent}
                            onChange={(e) => setNewMemoryContent(e.target.value)}
                            placeholder="记忆内容"
                            className="memory-edit-content"
                            rows={4}
                          />
                          <div className="memory-edit-actions">
                            <button
                              onClick={() => {
                                if (newMemoryTitle.trim() && newMemoryContent.trim()) {
                                  handleCreateMemory(newMemoryTitle, newMemoryContent);
                                } else {
                                  alert('请填写标题和内容');
                                }
                              }}
                              className="memory-save-btn"
                            >
                              保存
                            </button>
                            <button
                              onClick={() => {
                                setShowAddMemoryForm(false);
                                setNewMemoryTitle('');
                                setNewMemoryContent('');
                              }}
                              className="memory-cancel-btn"
                            >
                              取消
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                    {conversationMemories.length === 0 && !showAddMemoryForm ? (
                    <div className="empty-memories">
                      <div className="empty-icon">🧠</div>
                      <div className="empty-text">暂无记忆</div>
                      <div className="empty-hint">在对话中保存重要信息为记忆</div>
                    </div>
                  ) : (
                    conversationMemories.map((memory) => (
                      <div key={memory.id} className="memory-item">
                        {editingMemoryId === memory.id ? (
                          <div className="memory-edit">
                            <input
                              type="text"
                              defaultValue={memory.title}
                              placeholder="记忆标题"
                              className="memory-edit-title"
                            />
                            <textarea
                              defaultValue={memory.content}
                              placeholder="记忆内容"
                              className="memory-edit-content"
                              rows={4}
                            />
                            <div className="memory-edit-actions">
                              <button
                                onClick={(e) => {
                                  const memoryItem = e.currentTarget.closest('.memory-item');
                                  if (memoryItem) {
                                    const titleInput = memoryItem.querySelector('.memory-edit-title') as HTMLInputElement;
                                    const contentTextarea = memoryItem.querySelector('.memory-edit-content') as HTMLTextAreaElement;
                                    if (titleInput && contentTextarea) {
                                      handleUpdateMemory(memory.id, titleInput.value, contentTextarea.value);
                                    }
                                  }
                                }}
                                className="memory-save-btn"
                              >
                                保存
                              </button>
                              <button
                                onClick={() => setEditingMemoryId(null)}
                                className="memory-cancel-btn"
                              >
                                取消
                              </button>
                            </div>
                          </div>
                        ) : (
                          <>
                            <div className="memory-header">
                              <div className="memory-title">{memory.title}</div>
                              <div className="memory-actions">
                                <button
                                  onClick={() => setEditingMemoryId(memory.id)}
                                  title="编辑记忆"
                                  className="memory-edit-btn"
                                >
                                  ✏️
                                </button>
                                <button
                                  onClick={() => handleDeleteMemory(memory.id)}
                                  title="删除记忆"
                                  className="memory-delete-btn"
                                >
                                  🗑️
                                </button>
                              </div>
                            </div>
                            <div className="memory-content">{memory.content}</div>
                            <div className="memory-meta">
                              <span className="memory-date">
                                {(() => {
                                  try {
                                    const date = new Date(memory.created_at);
                                    // 如果日期无效，返回原字符串
                                    if (isNaN(date.getTime())) {
                                      return memory.created_at;
                                    }
                                    return date.toLocaleString('zh-CN', {
                                      year: 'numeric',
                                      month: '2-digit',
                                      day: '2-digit',
                                      hour: '2-digit',
                                      minute: '2-digit',
                                      second: '2-digit',
                                      hour12: false,
                                      timeZone: 'Asia/Shanghai'
                                    });
                                  } catch (e) {
                                    return memory.created_at;
                                  }
                                })()}
                              </span>
                              {memory.category && (
                                <span className="memory-category">{memory.category}</span>
                              )}
                            </div>
                          </>
                        )}
                      </div>
                    ))
                      )}
                    </div>
                  </div>
                )}
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

