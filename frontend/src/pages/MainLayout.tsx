import { useState, useEffect, useRef } from 'react';
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { setAuthToken, authAPI, conversationAPI } from '../api';
import { useTheme } from '../contexts/ThemeContext';
import { handleError } from '../utils';
import ChatPage from './ChatPage';
import ProfilePage from './ProfilePage';
import './MainLayout.css';

interface User {
  id: number;
  username: string;
  email: string;
}

interface Conversation {
  id: number;
  title: string;
  message_count: number;
  last_message_at: string;
  created_at: string;
  updated_at: string;
  last_message_preview?: string;
}

export default function MainLayout() {
  const [activeTab, setActiveTab] = useState<'chat' | 'profile'>('chat');
  const [user, setUser] = useState<User | null>(null);
  const [showSettingsMenu, setShowSettingsMenu] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const settingsMenuRef = useRef<HTMLDivElement>(null);
  
  // 对话列表相关状态
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<number | null>(null);
  const [editingConversationId, setEditingConversationId] = useState<number | null>(null);
  const [selectedConversations, setSelectedConversations] = useState<Set<number>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    let isMounted = true;
    const loadData = async () => {
      try {
        const currentUser = await authAPI.getCurrentUser();
        if (isMounted) {
          setUser(currentUser);
        }
      } catch (err) {
        // 静默处理错误，不影响用户体验
      }
    };
    loadData();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    // 根据当前路径设置activeTab
    if (location.pathname === '/profile') {
      setActiveTab('profile');
    } else {
      setActiveTab('chat');
    }
  }, [location.pathname]);

  // 加载对话列表
  useEffect(() => {
    if (activeTab === 'chat') {
      loadConversations();
    }
  }, [activeTab]);

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

  const handleEditConversation = async (conversationId: number, newTitle: string) => {
    try {
      await conversationAPI.updateConversation(conversationId, { title: newTitle });
      await loadConversations();
      setEditingConversationId(null);
    } catch (err) {
      handleError(err, '更新对话标题失败');
    }
  };

  const handleBatchDelete = async () => {
    if (selectedConversations.size === 0) return;
    if (!confirm(`确定要删除选中的 ${selectedConversations.size} 个对话吗？`)) return;
    try {
      await conversationAPI.batchDeleteConversations(Array.from(selectedConversations));
      if (currentConversationId && selectedConversations.has(currentConversationId)) {
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

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (settingsMenuRef.current && !settingsMenuRef.current.contains(event.target as Node)) {
        setShowSettingsMenu(false);
      }
    };

    if (showSettingsMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showSettingsMenu]);

  const handleLogout = async (e: React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.stopPropagation();
    
    try {
      await authAPI.logout();
    } catch (err) {
      // 即使logout API失败，也继续清除本地状态
    }
    
    // 无论API调用是否成功，都清除本地状态
    setAuthToken(null);
    setUser(null);
    localStorage.removeItem('token');
    window.location.href = '/login';
  };

  const getInitials = (username: string) => {
    return username.charAt(0).toUpperCase();
  };

  return (
    <div className="main-layout">
      <div className="sidebar">
        <div className="sidebar-header">
          <h2>LMQA</h2>
        </div>
        <nav className="sidebar-nav">
          <button
            className={activeTab === 'chat' ? 'active' : ''}
            onClick={() => {
              setActiveTab('chat');
              navigate('/');
            }}
          >
            <span>💬</span>
            <span>对话</span>
          </button>
          <button
            className={activeTab === 'profile' ? 'active' : ''}
            onClick={() => {
              setActiveTab('profile');
              navigate('/profile');
            }}
          >
            <span>⚙️</span>
            <span>个人设置</span>
          </button>
        </nav>
        
        {/* 对话列表区域 - 只在对话页面显示 */}
        {activeTab === 'chat' && (
          <>
            <div className="sidebar-divider"></div>
            <div className="sidebar-conversations">
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
              {selectedConversations.size > 0 && (
                <div className="batch-actions">
                  <span>已选择 {selectedConversations.size} 个</span>
                  <button onClick={handleBatchDelete} className="batch-delete-btn">批量删除</button>
                  <button onClick={() => setSelectedConversations(new Set())}>取消</button>
                </div>
              )}
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
            </div>
          </>
        )}
        <div className="sidebar-footer">
          <button 
            onClick={handleLogout} 
            className="logout-btn" 
            type="button"
          >
            <span style={{ pointerEvents: 'none' }}>退出登录</span>
          </button>
        </div>
      </div>
      <div className="main-content">
        <Routes>
          <Route 
            path="/" 
            element={
              <ChatPage 
                currentConversationId={currentConversationId}
                setCurrentConversationId={setCurrentConversationId}
                onConversationChange={loadConversations}
              />
            } 
          />
          <Route path="/profile" element={<ProfilePage />} />
        </Routes>
      </div>
      
      {/* 左下角用户信息和设置按钮 */}
      <div className="user-info-panel">
        {user && (
          <div className="user-info">
            <div className="user-avatar">
              {getInitials(user.username)}
            </div>
            <div className="user-details">
              <div className="user-name">{user.username}</div>
              <div className="user-email">{user.email}</div>
            </div>
          </div>
        )}
        <div className="settings-button-wrapper" ref={settingsMenuRef}>
          <button
            className="settings-button"
            onClick={() => setShowSettingsMenu(!showSettingsMenu)}
            title="设置"
          >
            ⚙️
          </button>
          {showSettingsMenu && (
            <div className="settings-menu">
              <button onClick={toggleTheme}>
                {theme === 'light' ? '🌙' : '☀️'} {theme === 'light' ? '深色模式' : '浅色模式'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

