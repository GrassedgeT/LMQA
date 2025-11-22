import { useState, useEffect } from 'react';
import { authAPI } from '../api';
import { handleError } from '../utils';
import './ProfilePage.css';

export default function ProfilePage() {
  const [user, setUser] = useState<{ id: number; username: string; email: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'profile' | 'password'>('profile');
  
  // 用户信息表单
  const [profileForm, setProfileForm] = useState({
    username: '',
    email: '',
  });
  
  // 密码表单
  const [passwordForm, setPasswordForm] = useState({
    oldPassword: '',
    newPassword: '',
    confirmPassword: '',
  });

  useEffect(() => {
    loadUser();
  }, []);

  const loadUser = async () => {
    try {
      setLoading(true);
      const userData = await authAPI.getCurrentUser();
      setUser(userData);
      setProfileForm({
        username: userData.username,
        email: userData.email,
      });
    } catch (err) {
      handleError(err, '加载用户信息失败');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateProfile = async () => {
    if (!profileForm.username.trim() || !profileForm.email.trim()) {
      alert('用户名和邮箱不能为空');
      return;
    }

    try {
      setLoading(true);
      const updatedUser = await authAPI.updateUser({
        username: profileForm.username.trim(),
        email: profileForm.email.trim(),
      });
      setUser(updatedUser);
      alert('用户信息更新成功');
    } catch (err) {
      handleError(err, '更新用户信息失败');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdatePassword = async () => {
    if (!passwordForm.oldPassword || !passwordForm.newPassword) {
      alert('请填写所有密码字段');
      return;
    }

    if (passwordForm.newPassword.length < 8) {
      alert('新密码长度至少8个字符');
      return;
    }

    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      alert('两次输入的新密码不一致');
      return;
    }

    try {
      setLoading(true);
      await authAPI.updatePassword(passwordForm.oldPassword, passwordForm.newPassword);
      alert('密码修改成功');
      setPasswordForm({
        oldPassword: '',
        newPassword: '',
        confirmPassword: '',
      });
    } catch (err) {
      handleError(err, '修改密码失败');
    } finally {
      setLoading(false);
    }
  };

  if (loading && !user) {
    return <div className="loading">加载中...</div>;
  }

  return (
    <div className="profile-page">
      <div className="profile-header">
        <h1>个人设置</h1>
      </div>

      <div className="profile-tabs">
        <button
          className={activeTab === 'profile' ? 'active' : ''}
          onClick={() => setActiveTab('profile')}
        >
          个人信息
        </button>
        <button
          className={activeTab === 'password' ? 'active' : ''}
          onClick={() => setActiveTab('password')}
        >
          修改密码
        </button>
      </div>

      <div className="profile-content">
        {activeTab === 'profile' && (
          <div className="profile-form">
            <div className="form-group">
              <label>用户名</label>
              <input
                type="text"
                value={profileForm.username}
                onChange={(e) => setProfileForm({ ...profileForm, username: e.target.value })}
                placeholder="输入用户名"
              />
            </div>
            <div className="form-group">
              <label>邮箱</label>
              <input
                type="email"
                value={profileForm.email}
                onChange={(e) => setProfileForm({ ...profileForm, email: e.target.value })}
                placeholder="输入邮箱"
              />
            </div>
            <button
              onClick={handleUpdateProfile}
              disabled={loading}
              className="save-btn"
            >
              {loading ? '保存中...' : '保存更改'}
            </button>
          </div>
        )}

        {activeTab === 'password' && (
          <div className="profile-form">
            <div className="form-group">
              <label>原密码</label>
              <input
                type="password"
                value={passwordForm.oldPassword}
                onChange={(e) => setPasswordForm({ ...passwordForm, oldPassword: e.target.value })}
                placeholder="输入原密码"
              />
            </div>
            <div className="form-group">
              <label>新密码</label>
              <input
                type="password"
                value={passwordForm.newPassword}
                onChange={(e) => setPasswordForm({ ...passwordForm, newPassword: e.target.value })}
                placeholder="输入新密码（至少8个字符）"
              />
            </div>
            <div className="form-group">
              <label>确认新密码</label>
              <input
                type="password"
                value={passwordForm.confirmPassword}
                onChange={(e) => setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })}
                placeholder="再次输入新密码"
              />
            </div>
            <button
              onClick={handleUpdatePassword}
              disabled={loading}
              className="save-btn"
            >
              {loading ? '修改中...' : '修改密码'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

