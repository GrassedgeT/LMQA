# 如果使用AI写代码，注意不要让AI随便破坏别人写的文件
# 所有依赖不要让AI安装，必须根据依赖的文档自己手动管理
# commit message注意遵守[commit convince](https://www.conventionalcommits.org/en/v1.0.0/)
# 所有API KEY不能硬编码到代码中，一律使用.env文件获取，不push到remote

# git注意事项
开发自己功能前一定要从主分支上创建一个自己的新分支，自己的提交push到自己的分支上，想合并到主分支请通过发起pr
在 Push 之前，必须拉取远端最新代码，以避免覆盖他人代码。推荐使用 rebase 保持提交线整洁
```
# 获取远端更新（不合并）
git fetch origin

# 将你的修改“变基”到最新的 origin/main 之上
# 如果有冲突，解决冲突后 git add <file> 然后 git rebase --continue
git rebase origin/main

# 推送到远端
git push -u origin feature/my-new-feature

# 想要合并到主分支请在GitHub 网页端发起 Pull Request (PR)
```
# LMQA - React + Flask 前后端交互演示

这是一个最小的React + Flask前后端交互演示项目，展示了如何构建一个完整的Web应用程序。

## 项目结构

```
.
├── backend/          # Flask后端
│   ├── main.py       # 主应用程序文件
│   ├── pyproject.toml # 依赖管理
│   └── README.md     # 后端说明
└── frontend/         # React前端
    ├── src/          # 源代码
    ├── package.json  # 依赖管理
    └── README.md     # 前端说明
```

## 功能特性

- 前后端分离架构
- RESTful API设计
- 跨域请求处理
- 待办事项管理（CRUD操作）
- 错误处理和加载状态

## 运行说明

### 必要依赖（自己下载）
uv包管理器（管理python），npm(前端)

### 后端 (Flask)

1. 进入后端目录：
   ```
   cd backend
   ```

2. 安装依赖：
   ```
   uv sync
   ```

3. 激活虚拟环境

   windows使用.venv/bin下的activate.ps1或activate.bat, linux下根据自己的shell类型选择相应的activate脚本
   ```
   source .venv/bin/activate
   ```

3. 运行开发服务器：
   ```
   uv run main.py
   ```
4. 注意：
* 所有python相关的依赖使用 'uv add xxx' 进行安装，不要使用 'pip install' ,如果 uv add 不好使，再考虑使用 'uv pip install xxx'
* 运行python脚本使用 'uv run xxx.py' , 不要使用'python xxx.py'
   后端服务器将在 http://localhost:5000 上运行

### 前端 (React + Vite)

1. 进入前端目录：
   ```
   cd frontend
   ```

2. 安装依赖：
   ```
   npm install
   ```

3. 运行开发服务器：
   ```
   npm run dev
   ```
其他前端依赖根据依赖的官方文档使用npm进行管理
   服务器将在 http://localhost:3000 上运行

### 同时运行前后端

推荐使用两个终端分别运行前后端服务：

终端1（后端）：
```bash
cd backend
uv run main.py
```

终端2（前端）：
```bash
cd frontend
npm run dev
```

访问 http://localhost:3000 查看应用程序。

## API端点

后端提供以下API端点：

- `GET /api/todos` - 获取所有待办事项
- `POST /api/todos` - 创建新的待办事项
- `PUT /api/todos/<id>` - 更新待办事项
- `DELETE /api/todos/<id>` - 删除待办事项

## 开发范式

这个项目展示了以下开发范式：

1. **前后端分离**：前端和后端完全独立，通过API进行通信
2. **RESTful设计**：遵循REST原则设计API端点
3. **跨域处理**：使用CORS处理开发环境中的跨域请求
4. **错误处理**：前后端都包含适当的错误处理机制
5. **状态管理**：React使用useState进行本地状态管理
6. **代理配置**：Vite配置代理以简化开发环境中的API调用
