# Flask 后端服务

这是一个简单的Flask后端服务，提供RESTful API用于管理待办事项。

## 功能特性

- GET /api/todos - 获取所有待办事项
- POST /api/todos - 创建新的待办事项
- PUT /api/todos/<id> - 更新待办事项
- DELETE /api/todos/<id> - 删除待办事项

## API端点

### 获取所有待办事项
```
GET /api/todos
```

响应示例：
```json
[
  {
    "id": 1,
    "text": "学习React和Flask",
    "completed": false
  }
]
```

### 创建新的待办事项
```
POST /api/todos
Content-Type: application/json

{
  "text": "新的待办事项"
}
```

响应示例：
```json
{
  "id": 2,
  "text": "新的待办事项",
  "completed": false
}
```

### 更新待办事项
```
PUT /api/todos/1
Content-Type: application/json

{
  "completed": true
}
```

响应示例：
```json
{
  "id": 1,
  "text": "学习React和Flask",
  "completed": true
}
```

### 删除待办事项
```
DELETE /api/todos/1
```

响应示例：
```json
{
  "id": 1,
  "text": "学习React和Flask",
  "completed": true
}