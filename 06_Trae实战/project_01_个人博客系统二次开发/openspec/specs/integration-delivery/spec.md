# integration-delivery Specification

## Purpose

打通前后端通信与静态托管，完成基本异常测试与一键启动部署，确保博客系统可正常访问和使用。

## Requirements

### Requirement: SPA 单页托管
系统 SHALL 在根路径 `/` 返回 `index.html`，支持前端单页应用通过后端托管访问。

#### Scenario: 访问首页
- **WHEN** 用户在浏览器访问 `http://127.0.0.1:8000/`
- **THEN** 返回 `index.html` 文件内容，Content-Type 为 `text/html`

#### Scenario: API 路由不受影响
- **WHEN** 用户访问 `/api/posts` 或 `/api/categories`
- **THEN** 正常返回 JSON 数据，不受 SPA 路由影响

### Requirement: CORS 跨域配置
系统 SHALL 配置 CORS 中间件，允许任意来源的跨域请求。

#### Scenario: 跨域请求
- **WHEN** 任意客户端发起跨域 API 请求
- **THEN** 服务端正确响应，不被浏览器 CORS 策略拦截

### Requirement: 全链路功能验收
系统 SHALL 支持完整的文章 CRUD 操作，前后端联调正常。

#### Scenario: 文章创建
- **WHEN** 用户填写标题与 Markdown 正文点击发布
- **THEN** 列表立即新增卡片，数据库成功写入

#### Scenario: 详情与计数
- **WHEN** 点击卡片打开详情模态框
- **THEN** Markdown 正确渲染，阅读量自增 1

#### Scenario: 文章编辑
- **WHEN** 点击编辑修改标题与内容后保存
- **THEN** 列表与详情同步更新

#### Scenario: 文章删除
- **WHEN** 确认删除指定文章
- **THEN** 列表卡片移除，数据库物理删除

#### Scenario: 分类筛选
- **WHEN** 点击分类胶囊标签
- **THEN** 列表仅显示该分类下的文章

#### Scenario: 搜索过滤
- **WHEN** 输入关键词
- **THEN** 列表即时过滤包含该词的文章
