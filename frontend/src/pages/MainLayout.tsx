import { useState, useEffect, useRef } from 'react';
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { setAuthToken, authAPI } from '../api';
import { useTheme } from '../contexts/ThemeContext';
import ChatPage from './ChatPage';
import MemoryPage from './MemoryPage';
import ProfilePage from './ProfilePage';
import './MainLayout.css';

interface User {
  id: number;
  username: string;
  email: string;
}

export default function MainLayout() {
  const [activeTab, setActiveTab] = useState<'chat' | 'memory' | 'profile'>('chat');
  const [user, setUser] = useState<User | null>(null);
  const [showSettingsMenu, setShowSettingsMenu] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const settingsMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadUser();
  }, []);

  useEffect(() => {
    // 根据当前路径设置activeTab
    if (location.pathname === '/memories') {
      setActiveTab('memory');
    } else if (location.pathname === '/profile') {
      setActiveTab('profile');
    } else {
      setActiveTab('chat');
    }
  }, [location.pathname]);

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

  const loadUser = async () => {
    try {
      const currentUser = await authAPI.getCurrentUser();
      setUser(currentUser);
    } catch (err) {
      console.error('加载用户信息失败:', err);
    }
  };

  const handleLogout = () => {
    setAuthToken(null);
    navigate('/login');
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
            className={activeTab === 'memory' ? 'active' : ''}
            onClick={() => {
              setActiveTab('memory');
              navigate('/memories');
            }}
          >
            <span>🧠</span>
            <span>记忆管理</span>
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
        <div className="sidebar-footer">
          <button onClick={handleLogout} className="logout-btn">
            退出登录
          </button>
        </div>
      </div>
      <div className="main-content">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/memories" element={<MemoryPage />} />
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

