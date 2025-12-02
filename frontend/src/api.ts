// API服务层 - 统一封装所有API调用

const API_BASE = '/api';
const MAX_RETRIES = 3;
const RETRY_DELAY = 1000; // 毫秒

// 存储token
let authToken: string | null = localStorage.getItem('token');

export const setAuthToken = (token: string | null) => {
  authToken = token;
  if (token) {
    localStorage.setItem('token', token);
  } else {
    localStorage.removeItem('token');
  }
};

export const getAuthToken = () => authToken;

/**
 * 延迟函数
 */
const delay = (ms: number): Promise<void> => new Promise(resolve => setTimeout(resolve, ms));

/**
 * 统一请求函数（带重试机制）
 */
async function request<T>(
  endpoint: string, 
  options: RequestInit = {}, 
  retries: number = MAX_RETRIES
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };

  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    // 检查响应类型
    const contentType = response.headers.get('content-type') || '';
    let data: any;
    
    if (contentType.includes('application/json')) {
      try {
        data = await response.json();
      } catch (e) {
        // 即使content-type是JSON，解析失败也要处理
        const text = await response.text();
        if (response.status === 401) {
          setAuthToken(null);
          window.location.href = '/login';
          throw new Error('认证失败，请重新登录');
        }
        throw new Error('服务器返回了无效的JSON格式');
      }
    } else {
      // 非JSON响应，尝试读取文本
      const text = await response.text();
      if (response.status === 401) {
        setAuthToken(null);
        window.location.href = '/login';
        throw new Error('认证失败，请重新登录');
      }
      // 尝试解析为JSON（某些服务器可能设置了错误的content-type）
      try {
        data = JSON.parse(text);
      } catch (e) {
        throw new Error(`服务器返回了非JSON格式的响应: ${text.substring(0, 100)}`);
      }
    }

    if (!response.ok) {
      // Token过期，清除并跳转登录
      if (response.status === 401) {
        setAuthToken(null);
        window.location.href = '/login';
        throw new Error('认证失败，请重新登录');
      }
      
      // 对于服务器错误，如果是可重试的错误且还有重试次数，则重试
      if (response.status >= 500 && retries > 0) {
        await delay(RETRY_DELAY);
        return request<T>(endpoint, options, retries - 1);
      }
      
      throw new Error(data.message || data.error || `请求失败 (${response.status})`);
    }

    return data.data || data;
  } catch (error) {
    // 网络错误处理，如果是网络错误且还有重试次数，则重试
    if (
      error instanceof TypeError && 
      error.message.includes('fetch') && 
      retries > 0
    ) {
      await delay(RETRY_DELAY);
      return request<T>(endpoint, options, retries - 1);
    }
    
    // 如果是认证错误，不重试
    if (error instanceof Error && error.message.includes('认证失败')) {
      throw error;
    }
    
    // 其他错误，如果是网络错误且还有重试次数，则重试
    if (retries > 0 && !(error instanceof Error && error.message.includes('认证失败'))) {
      await delay(RETRY_DELAY);
      return request<T>(endpoint, options, retries - 1);
    }
    
    // 网络错误处理
    if (error instanceof TypeError && error.message.includes('fetch')) {
      throw new Error('网络连接失败，请检查网络设置');
    }
    
    throw error;
  }
}

// 认证API
export const authAPI = {
  register: async (username: string, email: string, password: string) => {
    return request('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, email, password }),
    });
  },

  login: async (username: string, password: string) => {
    const data = await request<{
      access_token: string;
      token_type: string;
      expires_in: number;
      user: { id: number; username: string; email: string };
    }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    setAuthToken(data.access_token);
    return data;
  },

  getCurrentUser: async () => {
    return request<{ id: number; username: string; email: string }>('/auth/me');
  },

  updateUser: async (userData: { username?: string; email?: string }) => {
    return request<{ id: number; username: string; email: string }>('/auth/me', {
      method: 'PUT',
      body: JSON.stringify(userData),
    });
  },

  updatePassword: async (oldPassword: string, newPassword: string) => {
    return request('/auth/password', {
      method: 'PUT',
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    });
  },

  refreshToken: async () => {
    const data = await request<{
      access_token: string;
      token_type: string;
      expires_in: number;
    }>('/auth/refresh', {
      method: 'POST',
    });
    setAuthToken(data.access_token);
    return data;
  },

  logout: async () => {
    try {
      // 尝试调用后端logout API（如果存在）
      await request('/auth/logout', {
        method: 'POST',
      });
    } catch (err) {
      // 如果后端没有logout API，忽略错误，继续清除本地token
    }
    // 注意：这里不在finally中清除token，因为MainLayout中的handleLogout会处理
  },
};

// 对话API
export const conversationAPI = {
  getConversations: async (page = 1, limit = 20) => {
    return request<{
      conversations: Array<{
        id: number;
        title: string;
        message_count: number;
        last_message_at: string;
        created_at: string;
        updated_at: string;
      }>;
      pagination: {
        page: number;
        limit: number;
        total: number;
        total_pages: number;
        has_next: boolean;
        has_prev: boolean;
      };
    }>(`/conversations?page=${page}&limit=${limit}`);
  },

  createConversation: async (title?: string) => {
    return request<{
      id: number;
      title: string;
      created_at: string;
    }>('/conversations', {
      method: 'POST',
      body: JSON.stringify({ title: title || '新对话' }),
    });
  },

  deleteConversation: async (conversationId: number) => {
    return request(`/conversations/${conversationId}`, {
      method: 'DELETE',
    });
  },

  updateConversation: async (conversationId: number, data: {
    title?: string;
    description?: string;
    is_pinned?: boolean;
    is_archived?: boolean;
    settings?: any;
  }) => {
    return request<{
      id: number;
      title: string;
      description?: string;
      is_pinned: boolean;
      is_archived: boolean;
      updated_at: string;
    }>(`/conversations/${conversationId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  batchDeleteConversations: async (conversationIds: number[]) => {
    return request<{ deleted_count: number }>('/conversations/batch', {
      method: 'DELETE',
      body: JSON.stringify({ conversation_ids: conversationIds }),
    });
  },

  getMessages: async (conversationId: number, page = 1, limit = 50) => {
    return request<{
      messages: Array<{
        id: number;
        role: 'user' | 'assistant';
        content: string;
        created_at: string;
      }>;
      pagination: {
        page: number;
        limit: number;
        total: number;
        total_pages: number;
      };
    }>(`/conversations/${conversationId}/messages?page=${page}&limit=${limit}`);
  },

  sendMessage: async (conversationId: number, content: string) => {
    return request<{
      user_message: {
        id: number;
        role: 'user';
        content: string;
        created_at: string;
      };
      assistant_message: {
        id: number;
        role: 'assistant';
        content: string;
        created_at: string;
      };
    }>(`/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
  },

  sendMessageStream: async (
    conversationId: number,
    content: string,
    onToken: (token: string) => void,
    onDone: (messageId: number) => void,
    onError: (error: string) => void,
    abortSignal?: AbortSignal
  ) => {
    const token = getAuthToken();
    const response = await fetch(`${API_BASE}/conversations/${conversationId}/messages/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ content }),
      signal: abortSignal,
    });

    if (!response.ok) {
      const error = await response.json();
      onError(error.message || '请求失败');
      return;
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) {
      onError('无法读取响应流');
      return;
    }

    let buffer = '';
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        if (abortSignal?.aborted) {
          reader.cancel();
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            // 事件类型，暂时不需要使用
            continue;
          }
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.substring(6));
              if (data.type === 'token') {
                onToken(data.content);
              } else if (data.type === 'done') {
                onDone(data.message_id);
                return;
              } else if (data.type === 'error') {
                onError(data.message || '未知错误');
                return;
              }
            } catch (e) {
              // 忽略解析错误
            }
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        // 用户取消，不报错
        return;
      }
      onError(err instanceof Error ? err.message : '读取流失败');
    }
  },

  updateMessage: async (conversationId: number, messageId: number, content: string) => {
    return request<{
      id: number;
      content: string;
      is_edited: boolean;
      edited_at: string;
    }>(`/conversations/${conversationId}/messages/${messageId}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    });
  },

  deleteMessage: async (conversationId: number, messageId: number) => {
    return request(`/conversations/${conversationId}/messages/${messageId}`, {
      method: 'DELETE',
    });
  },
};

// 记忆API
export const memoryAPI = {
  getMemories: async (conversationId: number, page = 1, limit = 20, category?: string, search?: string) => {
    const params = new URLSearchParams({
      page: page.toString(),
      limit: limit.toString(),
      conversation_id: conversationId.toString(),
    });
    if (category) params.append('category', category);
    if (search) params.append('search', search);

    return request<{
      memories: Array<{
        id: number;
        conversation_id?: number;
        title: string;
        content: string;
        category?: string;
        tags?: string;
        memory_type?: string;
        created_at: string;
        updated_at: string;
      }>;
      pagination: {
        page: number;
        limit: number;
        total: number;
        total_pages: number;
      };
    }>(`/memories?${params.toString()}`);
  },

  createMemory: async (memory: {
    title: string;
    content: string;
    conversation_id: number;
    category?: string;
    tags?: string[];
    memory_type?: string;
  }) => {
    return request<{
      id: number;
      conversation_id?: number;
      title: string;
      content: string;
      category?: string;
      tags?: string;
      created_at: string;
    }>('/memories', {
      method: 'POST',
      body: JSON.stringify(memory),
    });
  },

  updateMemory: async (memoryId: number, memory: {
    title?: string;
    content?: string;
    category?: string;
    tags?: string[];
    memory_type?: string;
    conversation_id?: number;
  }) => {
    return request<{
      id: number;
      conversation_id?: number;
      title: string;
      content: string;
      category?: string;
      tags?: string;
      updated_at: string;
    }>(`/memories/${memoryId}`, {
      method: 'PUT',
      body: JSON.stringify(memory),
    });
  },

  deleteMemory: async (memoryId: number) => {
    return request(`/memories/${memoryId}`, {
      method: 'DELETE',
    });
  },

  searchMemories: async (conversationId: number, query: string, limit = 10) => {
    return request<{
      memories: Array<{
        id: number;
        title: string;
        content: string;
        category?: string;
      }>;
    }>('/memories/search', {
      method: 'POST',
      body: JSON.stringify({ conversation_id: conversationId, query, limit }),
    });
  },
};

// 模型配置API
export const modelConfigAPI = {
  getProviders: async () => {
    return request<{
      providers: Record<string, {
        name: string;
        base_url: string;
        models: string[];
      }>;
    }>('/user/model-configs/providers');
  },

  getModelConfigs: async () => {
    return request<{
      configs: Array<{
        id: number;
        user_id: number;
        provider: string;
        model_name: string;
        base_url: string;
        is_default: number;
        created_at: string;
        updated_at: string;
      }>;
    }>('/user/model-configs');
  },

  getDefaultModelConfig: async () => {
    return request<{
      id: number;
      user_id: number;
      provider: string;
      model_name: string;
      base_url: string;
      is_default: number;
      created_at: string;
      updated_at: string;
    }>('/user/model-configs/default');
  },

  createModelConfig: async (config: {
    provider: string;
    model_name: string;
    api_key: string;
    base_url?: string;
    is_default?: boolean;
  }) => {
    return request<{ id: number }>('/user/model-configs', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  },

  updateModelConfig: async (configId: number, config: {
    provider?: string;
    model_name?: string;
    api_key?: string;
    base_url?: string;
    is_default?: boolean;
  }) => {
    return request(`/user/model-configs/${configId}`, {
      method: 'PUT',
      body: JSON.stringify(config),
    });
  },

  deleteModelConfig: async (configId: number) => {
    return request(`/user/model-configs/${configId}`, {
      method: 'DELETE',
    });
  },

  setDefaultModelConfig: async (configId: number) => {
    return request(`/user/model-configs/${configId}/set-default`, {
      method: 'PUT',
    });
  },

  testModelConfig: async (configId: number) => {
    return request<{ valid: boolean; message: string }>(`/user/model-configs/${configId}/test`, {
      method: 'POST',
    });
  },
};

