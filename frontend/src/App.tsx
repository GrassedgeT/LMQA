import { useState, useEffect } from 'react'
import reactLogo from './assets/react.svg'
import viteLogo from '/vite.svg'
import './App.css'

// 定义待办事项类型
interface Todo {
  id: number
  text: string
  completed: boolean
}

function App() {
  const [todos, setTodos] = useState<Todo[]>([])
  const [newTodo, setNewTodo] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 获取所有待办事项
  const fetchTodos = async () => {
    try {
      setLoading(true)
      const response = await fetch('/api/todos')
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      setTodos(data)
      setError(null)
    } catch (err) {
      console.error('获取待办事项失败:', err)
      setError('获取待办事项失败: ' + (err instanceof Error ? err.message : '未知错误'))
    } finally {
      setLoading(false)
    }
  }

  // 添加新待办事项
  const addTodo = async () => {
    if (!newTodo.trim()) return

    try {
      const response = await fetch('/api/todos', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text: newTodo }),
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const newTodoItem = await response.json()
      setTodos([...todos, newTodoItem])
      setNewTodo('')
      setError(null)
    } catch (err) {
      console.error('添加待办事项失败:', err)
      setError('添加待办事项失败: ' + (err instanceof Error ? err.message : '未知错误'))
    }
  }

  // 切换待办事项完成状态
  const toggleTodo = async (id: number) => {
    const todo = todos.find(t => t.id === id)
    if (!todo) return

    try {
      const response = await fetch(`/api/todos/${id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ completed: !todo.completed }),
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const updatedTodo = await response.json()
      setTodos(todos.map(t => t.id === id ? updatedTodo : t))
      setError(null)
    } catch (err) {
      console.error('更新待办事项失败:', err)
      setError('更新待办事项失败: ' + (err instanceof Error ? err.message : '未知错误'))
    }
  }

  // 删除待办事项
  const deleteTodo = async (id: number) => {
    try {
      const response = await fetch(`/api/todos/${id}`, {
        method: 'DELETE',
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      setTodos(todos.filter(t => t.id !== id))
      setError(null)
    } catch (err) {
      console.error('删除待办事项失败:', err)
      setError('删除待办事项失败: ' + (err instanceof Error ? err.message : '未知错误'))
    }
  }

  // 组件挂载时获取待办事项
  useEffect(() => {
    fetchTodos()
  }, [])

  return (
    <>
      <div>
        <a href="https://vite.dev" target="_blank">
          <img src={viteLogo} className="logo" alt="Vite logo" />
        </a>
        <a href="https://react.dev" target="_blank">
          <img src={reactLogo} className="logo react" alt="React logo" />
        </a>
      </div>
      <h1>React + Flask 待办事项</h1>
      
      {/* 错误信息显示 */}
      {error && (
        <div className="error">
          错误: {error}
          <button onClick={fetchTodos}>重试</button>
        </div>
      )}
      
      {/* 添加新待办事项 */}
      <div className="add-todo">
        <input
          type="text"
          value={newTodo}
          onChange={(e) => setNewTodo(e.target.value)}
          placeholder="输入新的待办事项"
          onKeyDown={(e) => e.key === 'Enter' && addTodo()}
        />
        <button onClick={addTodo}>添加</button>
      </div>
      
      {/* 待办事项列表 */}
      <div className="todo-list">
        {loading ? (
          <p>加载中...</p>
        ) : (
          <>
            <h2>待办事项 ({todos.length})</h2>
            {todos.length === 0 ? (
              <p>暂无待办事项</p>
            ) : (
              <ul>
                {todos.map(todo => (
                  <li key={todo.id} className={todo.completed ? 'completed' : ''}>
                    <span onClick={() => toggleTodo(todo.id)}>
                      {todo.text}
                    </span>
                    <button onClick={() => deleteTodo(todo.id)}>删除</button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
      
      {/* 操作说明 */}
      <div className="instructions">
        <h3>操作说明</h3>
        <ul>
          <li>点击待办事项文本可切换完成状态</li>
          <li>点击"删除"按钮可删除待办事项</li>
          <li>在输入框中输入内容后按回车或点击"添加"按钮可添加新待办事项</li>
        </ul>
      </div>
    </>
  )
}

export default App
