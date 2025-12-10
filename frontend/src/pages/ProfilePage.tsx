import { useState, useEffect, useCallback } from 'react';
import { authAPI, modelConfigAPI } from '../api';
import { handleError, formatDateTime } from '../utils';
import MemoryPage from './MemoryPage';
import './ProfilePage.css';

interface ModelConfig {
  id: number;
  provider: string;
  model_name: string;
  base_url: string;
  is_default: number;
  created_at: string;
  updated_at: string;
}

interface Provider {
  name: string;
  base_url: string;
  models: string[];
}

export default function ProfilePage() {
  const [user, setUser] = useState<{ id: number; username: string; email: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'profile' | 'password' | 'model' | 'memory'>('profile');
  
  // 模型配置相关状态
  const [providers, setProviders] = useState<Record<string, Provider>>({});
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([]);
  const [editingConfig, setEditingConfig] = useState<ModelConfig | null>(null);
  const [showConfigForm, setShowConfigForm] = useState(false);
  const [configForm, setConfigForm] = useState({
    provider: '',
    model_name: '',
    api_key: '',
    base_url: '',
    is_default: false,
  });
  const [testingConfigId, setTestingConfigId] = useState<number | null>(null);
  
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

  // 模型配置相关函数
  const loadProviders = useCallback(async () => {
    try {
      const data = await modelConfigAPI.getProviders();
      // API 返回的数据结构可能是 { providers: {...} } 或直接是 providers
      setProviders(data?.providers || data || {});
    } catch (err) {
      console.error('加载模型提供商失败:', err);
      handleError(err, '加载模型提供商失败');
      // 即使失败也设置空对象，避免 UI 崩溃
      setProviders({});
    }
  }, []);

  const loadModelConfigs = useCallback(async () => {
    try {
      setLoading(true);
      const data = await modelConfigAPI.getModelConfigs();
      // API 返回的数据结构可能是 { configs: [...] } 或直接是 configs
      setModelConfigs(data?.configs || data || []);
    } catch (err) {
      console.error('加载模型配置失败:', err);
      handleError(err, '加载模型配置失败');
      // 即使失败也设置空数组，避免 UI 崩溃
      setModelConfigs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'model') {
      loadProviders();
      loadModelConfigs();
    }
  }, [activeTab, loadProviders, loadModelConfigs]);

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

  const handleSaveConfig = async () => {
    if (!configForm.provider || !configForm.model_name || !configForm.api_key) {
      alert('请填写所有必填字段');
      return;
    }

    try {
      setLoading(true);
      if (editingConfig) {
        await modelConfigAPI.updateModelConfig(editingConfig.id, {
          api_key: configForm.api_key,
          base_url: configForm.base_url || undefined,
          is_default: configForm.is_default,
        });
        alert('模型配置更新成功');
      } else {
        await modelConfigAPI.createModelConfig({
          provider: configForm.provider,
          model_name: configForm.model_name,
          api_key: configForm.api_key,
          base_url: configForm.base_url || undefined,
          is_default: configForm.is_default,
        });
        alert('模型配置创建成功');
      }
      setShowConfigForm(false);
      loadModelConfigs();
    } catch (err) {
      handleError(err, editingConfig ? '更新模型配置失败' : '创建模型配置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleEditConfig = (config: ModelConfig) => {
    setEditingConfig(config);
    setConfigForm({
      provider: config.provider,
      model_name: config.model_name,
      api_key: '', // 不显示已保存的 API Key
      base_url: config.base_url,
      is_default: config.is_default === 1,
    });
    setShowConfigForm(true);
  };

  const handleDeleteConfig = async (configId: number) => {
    if (!confirm('确定要删除这个模型配置吗？')) {
      return;
    }

    try {
      setLoading(true);
      await modelConfigAPI.deleteModelConfig(configId);
      alert('模型配置删除成功');
      loadModelConfigs();
    } catch (err) {
      handleError(err, '删除模型配置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSetDefault = async (configId: number) => {
    try {
      setLoading(true);
      await modelConfigAPI.setDefaultModelConfig(configId);
      alert('默认模型配置设置成功');
      loadModelConfigs();
    } catch (err) {
      handleError(err, '设置默认模型配置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleTestConfig = async (configId: number) => {
    try {
      setTestingConfigId(configId);
      const result = await modelConfigAPI.testModelConfig(configId);
      if (result.valid) {
        alert('API Key 测试成功！');
      } else {
        alert(`API Key 测试失败: ${result.message}`);
      }
    } catch (err) {
      handleError(err, '测试 API Key 失败');
    } finally {
      setTestingConfigId(null);
    }
  };

  if (loading && !user) {
    return (
      <div className="profile-page">
        <div className="loading" style={{ minHeight: '400px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          加载中...
        </div>
      </div>
    );
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
        <button
          className={activeTab === 'model' ? 'active' : ''}
          onClick={() => setActiveTab('model')}
        >
          模型配置
        </button>
        <button
          className={activeTab === 'memory' ? 'active' : ''}
          onClick={() => setActiveTab('memory')}
        >
          记忆管理
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

        {activeTab === 'model' && (
          <div className="model-config-content">
            <div className="model-config-header">
              <h2>大模型配置</h2>
              <button
                className="add-config-btn"
                onClick={() => {
                  setEditingConfig(null);
                  setConfigForm({
                    provider: '',
                    model_name: '',
                    api_key: '',
                    base_url: '',
                    is_default: false,
                  });
                  setShowConfigForm(true);
                }}
              >
                + 添加模型配置
              </button>
            </div>

            {showConfigForm && (
              <div className="config-form-modal">
                <div className="config-form-content">
                  <div className="config-form-header">
                    <h3>{editingConfig ? '编辑模型配置' : '添加模型配置'}</h3>
                    <button className="close-btn" onClick={() => setShowConfigForm(false)}>×</button>
                  </div>
                  <div className="config-form-body">
                    <div className="form-group">
                      <label>模型提供商</label>
                      <select
                        value={configForm.provider}
                        onChange={(e) => {
                          const provider = e.target.value;
                          setConfigForm({
                            ...configForm,
                            provider,
                            model_name: '',
                            base_url: providers[provider]?.base_url || '',
                          });
                        }}
                        disabled={!!editingConfig}
                      >
                        <option value="">选择提供商</option>
                        {Object.keys(providers).length > 0 ? (
                          Object.entries(providers).map(([key, provider]) => (
                            <option key={key} value={key}>{provider.name}</option>
                          ))
                        ) : (
                          <option value="" disabled>加载中...</option>
                        )}
                      </select>
                    </div>
                    {configForm.provider && (
                      <div className="form-group">
                        <label>模型名称</label>
                        <select
                          value={configForm.model_name}
                          onChange={(e) => setConfigForm({ ...configForm, model_name: e.target.value })}
                          disabled={!!editingConfig}
                        >
                          <option value="">选择模型</option>
                          {providers[configForm.provider]?.models.map((model) => (
                            <option key={model} value={model}>{model}</option>
                          ))}
                        </select>
                      </div>
                    )}
                    <div className="form-group">
                      <label>API Key</label>
                      <input
                        type="password"
                        value={configForm.api_key}
                        onChange={(e) => setConfigForm({ ...configForm, api_key: e.target.value })}
                        placeholder="输入 API Key"
                      />
                    </div>
                    <div className="form-group">
                      <label>Base URL (可选)</label>
                      <input
                        type="text"
                        value={configForm.base_url}
                        onChange={(e) => setConfigForm({ ...configForm, base_url: e.target.value })}
                        placeholder={configForm.provider ? providers[configForm.provider]?.base_url : 'Base URL'}
                      />
                    </div>
                    <div className="form-group">
                      <label>
                        <input
                          type="checkbox"
                          checked={configForm.is_default}
                          onChange={(e) => setConfigForm({ ...configForm, is_default: e.target.checked })}
                        />
                        设为默认模型
                      </label>
                    </div>
                    <div className="form-actions">
                      <button
                        className="save-btn"
                        onClick={handleSaveConfig}
                        disabled={loading || !configForm.provider || !configForm.model_name || !configForm.api_key}
                      >
                        {loading ? '保存中...' : '保存'}
                      </button>
                      <button
                        className="cancel-btn"
                        onClick={() => setShowConfigForm(false)}
                      >
                        取消
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {loading ? (
              <div className="loading" style={{ minHeight: '200px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'transparent' }}>
                加载中...
              </div>
            ) : (
              <div className="model-config-list">
                {modelConfigs.length === 0 ? (
                  <div className="empty-state">
                    <p>暂无模型配置，请添加一个模型配置</p>
                  </div>
                ) : (
                  modelConfigs.map((config) => {
                    const isDefault = config.is_default === 1;
                    return (
                      <div key={config.id} className={`config-item ${isDefault ? 'default' : ''}`}>
                        <div className="config-info">
                          <div className="config-header">
                            <h4>{providers[config.provider]?.name || config.provider} - {config.model_name}</h4>
                            {isDefault && <span className="default-badge">默认</span>}
                          </div>
                          <div className="config-details">
                            <p>Base URL: {config.base_url || '使用默认'}</p>
                            <p>创建时间: {formatDateTime(config.created_at)}</p>
                          </div>
                        </div>
                        <div className="config-actions">
                          <button
                            className="test-btn"
                            onClick={() => handleTestConfig(config.id)}
                            disabled={testingConfigId === config.id || loading}
                          >
                            {testingConfigId === config.id ? '测试中...' : '测试连接'}
                          </button>
                          {!isDefault && (
                            <button
                              className="set-default-btn"
                              onClick={() => handleSetDefault(config.id)}
                              disabled={loading}
                            >
                              设为默认
                            </button>
                          )}
                          <button
                            className="edit-btn"
                            onClick={() => handleEditConfig(config)}
                            disabled={loading}
                          >
                            编辑
                          </button>
                          <button
                            className="delete-btn"
                            onClick={() => handleDeleteConfig(config.id)}
                            disabled={loading}
                          >
                            删除
                          </button>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === 'memory' && (
          <div className="memory-tab-content">
            <MemoryPage />
          </div>
        )}
      </div>
    </div>
  );
}

