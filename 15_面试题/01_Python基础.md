# 15.1 Python 基础

> 🎯 **本节定位**：AI 把"写代码"的门槛打没了，面试官只能往更深的地方挖——**对象机制、并发模型、工程习惯**。这些题的价值不在"背过答案"，而在于你能不能讲清楚"为什么"，并能立刻举出 Agent 开发里的对应场景。
>
> 使用方式：每题先**自己口头答一遍**（像在面试现场），再对照"参考答案"检查差异；答不上来的题，把它当成小项目做一遍，比背十遍记得牢。

---

## 一、语言核心：数据模型与对象机制

### 1. 可变对象与不可变对象
**真实问法**："Python 里哪些对象可变、哪些不可变？可变对象作函数默认参数为什么会出事？"

**考察点**：对象机制 + 面试最高频的坑之一。

**参考答案**：

先分类：`list` / `dict` / `set`（以及自定义类实例）**可变**；`int` / `str` / `tuple` / `frozenset` **不可变**。不可变意味着任何修改操作（如字符串拼接、整数加减）都会**产生一个新对象**，而不是改原对象。

可变默认参数是经典的坑：`def f(items=[]):` 里的 `[]` 在**函数定义时只创建一次**，之后每次调用（不传该参数）拿到的都是**同一个 list**。所以：

```python
def add_item(x, items=[]):
    items.append(x)
    return items

add_item(1)   # [1]
add_item(2)   # [1, 2]  ← 上一次的结果还在，函数"带记忆"了
```

这在多用户/多请求共享状态时就是 bug 源头。标准改法是"None 哨兵"：

```python
def add_item(x, items=None):
    if items is None:
        items = []
    items.append(x)
    return items
```

**加分项**：补一句 `tuple` 里放 `list` 仍是可变的——不可变只保证"最外层引用不能换"，不保证深层不可变；这正是"浅不可变 vs 深不可变"的区别，也解释了为什么"含 list 的 tuple 不能哈希"。

---

### 2. `==` 与 `is`
**真实问法**："`==` 和 `is` 的区别？为什么 `a=256; b=256; a is b` 是 `True`，而 `a=257; b=257; a is b` 是 `False`？"

**考察点**：值相等 vs 身份相同 + 解释器驻留机制。

**参考答案**：

- `==` 比较**值**（可被 `__eq__` 重写）；`is` 比较**身份**，即 `id()` 是否相同（内存地址）。
- 区别在"两个对象内容一样" vs "就是同一个对象"。

小整数驻留（interning）是 CPython 的实现细节：解释器启动时把 `[-5, 256]` 的整数**预先创建并缓存**，所以范围内赋值取到的是同一个对象，`is` 为 `True`。**超过范围就不保证**：在交互式 REPL 里（每条语句单独编译），`a=257; b=257` 是两个独立对象，`is` 为 `False`；但在**同一代码块**（一个函数/脚本）里，编译器会把相同的字面量常量去重，`257` 可能又是同一个对象——所以"超范围必为 False"只在 REPL 逐行输入时稳定成立。字符串驻留也只发生在**部分场景**（如标识符、常量折叠），同样是未公开保证的实现细节。

工程上：**判断 `None` 或单例用 `is`，其余一律 `==`**——`is` 的行为依赖解释器实现细节，把它当"身份比较"用才对。

```python
# REPL 里逐行执行（经典面试现场）：
a, b = 256, 256
a is b          # True（小整数缓存）
c, d = 257, 257
c is d          # False（超范围，两个对象）——但 c == d 是 True
e = None
e is None       # True，判空的标准写法
```

**加分项**：结合具体场景讲，比如缓存命中判断、工具返回是否为 `None`——`is None` 是约定俗成且更快的写法，`== None` 会被 Lint 工具标记为错误风格。

---

### 3. 深浅拷贝
**真实问法**："浅拷贝和深拷贝的区别？`dict` 的浅拷贝有哪几种写法？嵌套列表改内层会不会互相影响？"

**考察点**：引用语义，Agent 开发里共享上下文/状态时最容易踩。

**参考答案**：

- **浅拷贝**（`copy.copy`）只复制最外层容器，**内层元素仍是同一个引用**；
- **深拷贝**（`copy.deepcopy`）递归复制所有层级，得到完全独立的对象。

`dict` 的浅拷贝三种等价写法：`b = a.copy()`、`b = dict(a)`、`b = {**a}`。它们都只新建外层 dict，内层对象共享：

```python
a = {"config": {"retries": 3}}
b = a.copy()                  # 浅拷贝
b["config"]["retries"] = 5
print(a["config"]["retries"]) # 5  ← 内层被改了！a 也被污染
```

深拷贝能解决这个问题，但它**很贵**：对巨大对象、循环引用对象递归复制，内存和耗时都不可忽略。生产里更常见的是**"只拷贝要改的字段"（写时复制）**：

```python
c = {**a, "config": {**a["config"], "retries": 5}}   # 只把要改的那一层换新
```

**加分项**：这直接对应 Agent 里的"状态污染"问题——多轮对话里如果直接改上游共享的 state dict，会串味；正确姿势是"读共享、写副本"。

---

### 4. 装饰器
**真实问法**："写一个带参数的装饰器。为什么装饰器里要加 `functools.wraps`？装饰器什么时候执行？"

**考察点**：闭包 + 元编程，是"中间件/护栏"的实现基础。

**参考答案**：

装饰器是语法糖：`@deco` 等价于 `fn = deco(fn)`。带参数的装饰器需要**三层函数**：外层接参数，中层接函数，内层接调用参数。

```python
from functools import wraps

def retry(max_times=3):                      # ① 外层：接装饰器参数
    def decorator(fn):                       # ② 中层：接被装饰函数
        @wraps(fn)                           # 复制 __name__/__doc__/__module__
        def wrapper(*args, **kwargs):        # ③ 内层：接真实调用参数
            for attempt in range(max_times):
                try:
                    return fn(*args, **kwargs)
                except Exception:
                    if attempt == max_times - 1:
                        raise
            return None
        return wrapper
    return decorator

@retry(max_times=3)
def call_llm(prompt): ...
```

三个要点：

1. **`@wraps` 的作用**：不加的话，`call_llm.__name__` 会变成 `wrapper`，日志、调试、文档全部失真；`wraps` 把原函数的元信息拷过来（还带上 `__wrapped__`，保留原始引用链）。
2. **执行时机**：装饰器在**模块 import、函数定义那一刻**执行，不是在函数被调用时。所以"装饰器里做重活（连数据库、建客户端）"会让 import 变慢且难以测试。
3. **闭包本质**：`wrapper` 能访问 `fn`、`max_times`，靠的是闭包（外层变量绑定），不是全局变量。

**加分项**：Agent 里的**重试、超时、Token 计费、日志埋点**都是装饰器场景；提一个你实际写过的（比如给工具调用加重试 + 账单上报），比背概念有说服力。

---

### 5. 生成器与迭代器
**真实问法**："生成器为什么省内存？`yield` 和 `return` 的本质区别？"

**考察点**：惰性求值，流式处理与流式输出的底层。

**参考答案**：

**迭代器**是"可以逐个取出元素的对象"（实现了 `__iter__` / `__next__`）；**生成器**是"用函数写出来的迭代器"——函数体里有 `yield`，调用它不会执行函数体，而是返回一个生成器对象。

`yield` 与 `return` 的本质区别：

- `yield`：**暂停并保存现场**（局部变量、执行位置都在），下次 `next()` 从暂停处继续；
- `return`：**终止迭代**，触发 `StopIteration`（带 `return 值` 的话值挂在 `StopIteration.value` 上）。

省内存的核心是**惰性求值**——一次只算一个，不把整个序列放进内存：

```python
def read_lines(path):
    with open(path, encoding="utf-8") as f:
        for line in f:          # 文件对象本身就是惰性的
            yield line.strip()  # 逐行吐，绝不一次性读 10GB 进内存

total = sum(1 for _ in read_lines("huge.log"))   # 流式数行数，内存恒定
```

对比：列表推导式 `[x for x in ...]` 一次性生成整个列表；生成器表达式 `(x for x in ...)` 惰性求值。取舍是"能否多次遍历"（生成器只能消费一次）和"能否下标访问"（生成器不能）。

**加分项**：Agent 的 **SSE 流式输出**就是生成器思想——`yield` 一段 token 吐一段，首字延迟（TTFT）低，不用等全部 Token 算完；这正是"一边生成一边吐"的工程价值。

---

### 6. 闭包与作用域（含经典延迟绑定）
**真实问法**："下面代码输出什么？`funcs = [lambda x: x*i for i in range(3)]`，然后 `[f(1) for f in funcs]`？"

**考察点**：LEGB 作用域 + 闭包延迟绑定，几乎必考的送分/送命题。

**参考答案**：

输出 `[2, 2, 2]`。原因是**闭包绑定的是变量本身，不是变量当时的"值"**：三个 lambda 捕获的是同一个 `i`，而循环结束后 `i = 2`，所以三个函数用的是同一个"最终版 `i`"。

```python
funcs = [lambda x: x * i for i in range(3)]
[f(1) for f in funcs]   # [2, 2, 2]  ← 不是 [0, 1, 2]
```

修复三选一：

```python
# ① 默认参数快照：把当前 i 的值"拍"进参数
funcs = [lambda x, i=i: x * i for i in range(3)]   # [0, 1, 2]

# ② functools.partial 提前固定参数
from functools import partial
funcs = [partial(lambda x, i: x * i, i=i) for i in range(3)]

# ③ 在函数体内创建新的绑定（如用默认值或闭包工厂）
def make(i):
    return lambda x: x * i
funcs = [make(i) for i in range(3)]
```

作用域顺序是 **LEGB**：局部（Local）→ 外层（Enclosing）→ 全局（Global）→ 内建（Built-in）。修改外层变量用 `nonlocal`（闭包场景），修改全局用 `global`。

**加分项**：工具注册表 / 中间件配置里的"配置值被晚绑定"是同一类坑——注册时捕获的是配置**对象引用**，配置在别处被替换后行为悄悄变化；举一个你在 Agent 项目里遇到过的实例。

---

### 7. 上下文管理器
**真实问法**："`with` 的原理？`__exit__` 的参数是什么？怎么用 `contextlib.contextmanager` 写一个？"

**考察点**：资源管理，Agent 的 HTTP 会话、锁、缓存连接都在用。

**参考答案**：

`with` 语句调用协议：进入时执行 `__enter__`（返回的资源绑定到 `as` 后的变量），退出时执行 `__exit__`（清理资源）。**无论函数体是否抛异常，`__exit__` 都会被执行**——这正是资源释放的兜底保证。

```python
class LockContext:
    def __init__(self, lock):            # 持有一个外部锁
        self.lock = lock
    def __enter__(self):
        self.lock.acquire()
        return self.lock
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()     # 异常与否都会执行
        return False            # 返回 True 吞掉异常；False 则继续抛
```

`__exit__` 的三个参数：`exc_type`（异常类型）、`exc_val`（异常实例）、`exc_tb`（traceback）。没有异常时三者都是 `None`。**返回 `True` 会吞掉异常**（慎用，容易把 bug 藏起来）；`False`（默认）让异常继续传播。

用 `contextlib.contextmanager` 把生成器变成上下文管理器更简洁——`yield` 之前是进入逻辑，之后是退出逻辑：

```python
from contextlib import contextmanager

@contextmanager
def timed_block(name):
    import time
    t0 = time.perf_counter()
    yield                                    # yield 出去的是 as 绑定的值
    print(f"{name} 耗时 {time.perf_counter() - t0:.3f}s")

with timed_block("工具调用"):
    call_tool()
```

**加分项**：讲清"`with` ≈ `try/finally`"的等价关系，以及多资源写法 `with A() as a, B() as b:`；再点一句"文件、锁、HTTP 会话、数据库连接，凡是需要'用完必还'的东西都用 `with`"。

---

## 二、高频考点：异常、并发与 GIL

### 8. GIL 是什么，怎么绕
**真实问法**："GIL 是什么？对多线程、多进程、异步的影响分别是什么？CPU 密集和 IO 密集怎么选？"

**考察点**：并发模型理解，Agent 服务稳定性的命门。

**参考答案**：

GIL（Global Interpreter Lock，全局解释器锁）是 CPython 的一个锁：**同一时刻只允许一个线程执行 Python 字节码**。它存在的历史原因是 CPython 的引用计数内存管理需要线程安全，用一把全局锁最简单。

三个关键推论：

1. **IO 密集 → 多线程够用**：线程在等待 IO（网络、磁盘、`time.sleep`）时会**释放 GIL**，另一个线程趁机执行。所以"等网络/等模型返回"这种场景，多线程能并行。
2. **CPU 密集 → 多线程无效**：纯计算不释放 GIL，多线程轮流抢锁反而更慢；必须**多进程**（`multiprocessing`/`ProcessPoolExecutor`）或交给 numpy/C 扩展（释放 GIL）。
3. **asyncio 是单线程协作式**：没有锁竞争，靠 `await` 主动让出控制权，适合"大量并发等待"；但一个阻塞调用会卡死整个循环。

选型一句话：**高并发 IO 用 asyncio，CPU 计算用多进程，不得不调同步阻塞库用线程池兜底**。三者还能组合。

**加分项**：Agent 主战场是"等模型、等网络"，CPU 计算占比极低，所以 asyncio + 少量线程池是标配；再补一句 3.13 已提供**可选的无 GIL 构建**（free-threaded），但生态兼容仍是问题，生产默认还是带 GIL 的 CPython。

---

### 9. 异常处理最佳实践
**真实问法**："`except Exception` 和 `except BaseException` 的区别？`try/except/else/finally` 各自什么时候执行？"

**考察点**：异常机制 + 工程规范。

**参考答案**：

异常继承树顶层是 `BaseException`，`Exception` 是它的子类。`KeyboardInterrupt`、`SystemExit`、`GeneratorExit` 直接继承 `BaseException`，**不是 `Exception`**——所以 `except Exception:` 不会误拦 Ctrl+C 和系统退出，这是刻意的设计：程序级事件不该被业务代码吞掉。

四个子句的执行顺序：

- `try`：执行可能出错的代码；
- `except`：**有异常且类型匹配**时执行；
- `else`：**没有异常**时执行（放"成功路径"代码，避免被 except 误包）；
- `finally`：**无论如何都执行**（即使 return，也会先执行 finally 再返回）。

```python
try:
    resp = call_tool()
except ToolTimeout as e:
    log.warning(f"超时降级: {e}")        # 只捕获能处理的
    resp = fallback()
else:
    cache.store(resp)                    # 只有成功才缓存
finally:
    stats.record()                       # 一定执行：计费/埋点
```

工程规范：

- 别裸 `except:`（会连 `KeyboardInterrupt` 一起吞）；
- **只捕获你能处理的异常**，处理不了就让它抛；
- 用 `raise ... from e` 保留异常链，排查时能一路追到根因。

**加分项**：Agent 工具调用失败的完整链路——"捕获 → 记录 → 降级/重试 → **把错误信息带回给 LLM 决策**"，这条链路里 `raise ... from` 保证错误根因不丢失。

---

### 10. asyncio：协程与事件循环
**真实问法**："协程、`await`、事件循环是什么关系？async 函数里能直接调 `requests.get` 吗？"

**考察点**：异步本质，很多人口头会背、一写就错。

**参考答案**：

- **协程**（coroutine）是"可以被暂停和恢复的函数"——`async def` 定义，调用它返回一个协程对象，**函数体不会立即执行**；
- **`await`** 是暂停点：把控制权交还**事件循环**，等被等待的对象就绪后再回来继续；
- **事件循环**（event loop）是调度器：单线程里维护一个就绪队列，谁的数据到了就轮到谁执行。

async 函数里**不能直接调阻塞的 `requests.get`**：它会卡住整个事件循环，所有并发请求一起变慢——就像单行道上一辆车抛锚，整条路堵死。

```python
import asyncio, httpx

async def fetch(url):
    async with httpx.AsyncClient() as client:   # 用异步客户端
        r = await client.get(url)               # await 让出控制权
        return r.text

async def main():
    results = await asyncio.gather(
        fetch("https://a.com"), fetch("https://b.com"),
    )                                           # 并发发两个请求
    return results

# asyncio.run(main())   # 入口（Jupyter 里用 await main()）
```

注意点：Jupyter / IPython 里事件循环已存在，直接 `await` 即可，别再套 `asyncio.run()`（会报"循环已在运行"）。

**加分项**：Agent 同时并发调用多个工具、多个模型 API 时，异步是吞吐的关键；`asyncio.gather` 配合"部分失败不阻塞整体"可以用 `return_exceptions=True`。

---

### 11. 同步阻塞代码怎么接入异步
**真实问法**："有个同步的 SDK（比如 OpenAI 同步客户端），在 async 代码里怎么调用而不阻塞？"

**考察点**：异步与同步的桥接，Agent 工具封装的标准动作。

**参考答案**：

三个方案，从省事到彻底：

1. **`asyncio.to_thread`**（3.9+）：把同步函数丢进默认线程池，外层 `await` 等结果——最省事：

```python
import asyncio
from openai import OpenAI

client = OpenAI()                       # 同步客户端

async def call_llm(prompt: str) -> str:
    return await asyncio.to_thread(     # 在线程池里执行，不阻塞事件循环
        client.chat.completions.create,
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
```

2. **`loop.run_in_executor(None, fn, ...)`**：`to_thread` 的底层，可以指定自定义线程池（比如限制并发度）。

3. **换用官方异步客户端**（`AsyncOpenAI` / `httpx.AsyncClient`）：真正异步、无线程切换开销，是最优解；前提是 SDK 提供 async 版本。

三个坑：① 线程池默认上限（`min(32, CPU+4)`），高并发下会排队；② **纯 CPU 任务丢线程池没用**（GIL 不释放）；③ 不要在线程池里再开 event loop。

**加分项**：讲成你封装过的真实函数签名——"我给工具层统一包了一层 `async def run_tool(name, **kw): return await asyncio.to_thread(dispatch, name, **kw)`"，面试官一听就知道你有实战。

---

### 12. 并发三件套选型
**真实问法**："多线程、多进程、asyncio 各适合什么？Agent 服务为什么常是 asyncio + 线程池？"

**考察点**：选型能力，比"会不会用"更值钱。

**参考答案**：

| 方案 | 开销 | 适用 | GIL 影响 |
| :--- | :--- | :--- | :--- |
| 多线程 | 中 | IO 密集（等网络/等模型） | 影响小（等待时释放 GIL） |
| 多进程 | 高 | CPU 密集、需要隔离 | 绕过 GIL，但 IPC 成本高 |
| asyncio | 低 | 高并发 IO，单线程协作 | 无竞争（单线程） |

选型逻辑：

- **CPU 密集**（图像解码、向量计算）→ 多进程；但 Python 场景里大量计算已下沉到 C 扩展（numpy/pytorch，自己释放 GIL），此时线程也行；
- **IO 密集 + 高并发**（Agent 服务、爬虫、API 网关）→ asyncio，单线程撑几万连接，开销最小；
- **IO 密集 + 并发量不高 / 要调同步库** → 多线程最省心；
- **组合**：asyncio 主循环 + `to_thread` 线程池兜底同步调用 + `ProcessPoolExecutor` 兜 CPU 重活。

Agent 服务选 asyncio + 线程池的理由：请求的本质是"等模型返回"，是纯 IO 等待；asyncio 把等待成本降到最低，而工具调用里总有同步 SDK，用线程池兜底，两者互补。

**加分项**：结合具体场景讲——"一次用户问题要并行召回 5 个工具，`asyncio.gather` 并发执行，谁先回谁先汇入上下文"，比背表格有画面。

---

### 13. 线程安全
**真实问法**："多线程同时改一个 `dict` 会怎样？怎么保证线程安全？"

**考察点**：并发下的共享状态，容易答成"GIL 保护一切"。

**参考答案**：

先说结论：**"GIL 保护一切"是误解**。GIL 只保证**单个字节码操作**基本原子（比如一次 `d[k]=v`），但**复合操作不安全**——"先查后改""先读后写"这种两步操作，中间可能被另一个线程插入。

```python
# 经典竞态：计数器
def inc():
    global count
    count += 1        # 这不是原子操作！= 读 count + 算 + 写 count，三步
```

两个线程同时 `count += 1`，可能都读到旧值、各自加一再写回，结果少加一次。

三种解法：

1. **加锁**：`threading.Lock` 包住临界区（最简单、最通用）：

```python
lock = threading.Lock()
with lock:
    count += 1
```

2. **用队列通信**：`queue.Queue` 本身线程安全，生产-消费模型里"别共享状态，用消息传"是更干净的架构。

3. **不可变/写时复制**：不共享可变状态，每次更新生成新对象（`functools.lru_cache` 之类自带锁）。

asyncio 里也有类似问题：**单线程不等于无竞争**——协程在 `await` 处切换，如果两个协程先后 `await` 同一段共享状态，逻辑上仍可能交错。

**加分项**：Agent 的记忆库、会话缓存是**跨请求共享**的，正确姿势是"读共享引用、写副本 + 锁"，或直接用 Redis 等外部存储做原子操作（呼应第六章数据库）。

---

## 三、工程习惯：类型、环境与测试

### 14. 类型标注与 Pydantic
**真实问法**："`Optional` 和 `Union` 的区别？`TypedDict` 和 `Protocol` 分别解决什么？和 Pydantic 是什么关系？"

**考察点**：工程素养，Agent 的结构化输出/配置系统全靠这个。

**参考答案**：

先分清两个层次：

- **类型标注**（`typing`）只对**静态检查**（mypy/pyright）和**阅读**有效，运行时不强制；
- **Pydantic** 在**运行时**做校验、转换、序列化，二者互补。

逐一回答：

- `Optional[X]` 就是 `Union[X, None]` 的语法糖，表示"可能是 X 也可能是 None"；
- `TypedDict` 给"普通 dict"标注形状，不改变运行时行为，只让静态检查知道你有哪些 key 和值类型：

```python
from typing import TypedDict

class ToolResult(TypedDict):
    tool: str
    output: str
    cost: float
```

- `Protocol` 描述**结构子类型**（鸭子类型）：只要对象有这些方法/属性就满足，不管它继承谁：

```python
from typing import Protocol

class Retriever(Protocol):
    def search(self, query: str, k: int = 5) -> list[str]: ...

def answer(r: Retriever, q: str): ...   # 任何有 search 方法的对象都能传
```

- **Pydantic**：`BaseModel` 定义类，实例化时**自动校验类型并转换**（"1" 能自动转成 int），`.model_dump()` 序列化、`.model_validate_json()` 反序列化。它是 Agent 的**配置系统**和 **LLM 结构化输出**的标准答案（配合 `response_format` 或工具参数 schema）。

**加分项**：工具函数的入参/出参用 `TypedDict` 定义后，直接喂给 LLM 当 function-calling 的 JSON schema；配置用 Pydantic `BaseModel` + 环境变量注入——把这两个组合讲出来，就是完整的"Agent 工程化"姿势。

---

### 15. 虚拟环境与依赖管理
**真实问法**："为什么现在都用 uv？它和 venv/pip/poetry 的区别？`requirements.txt` 和锁文件有什么区别？"

**考察点**：交付可复现性，"能跑"与"能交付"的分水岭。

**参考答案**：

**uv**（Rust 编写）火的原因：**快**（比 pip 快一个数量级）+ **一体化**——一个工具管 Python 解释器下载、虚拟环境、依赖安装、锁文件、发布，替代 venv/pip/poetry 的叠加组合。`uv add` / `uv run` / `uv lock` / `uv sync` 一条命令一个职责。

`requirements.txt` vs 锁文件的关键区别：

- `requirements.txt` 里常写的是**版本范围**（`langchain>=1.0`），每次安装解析出的**具体版本可能不同**；
- **锁文件**（`uv.lock` / `poetry.lock`）固定**每一个传递依赖的精确版本**+ 哈希：任何人在任何时间安装，得到的都是同一套字节级一致的环境。

工程结论：

- 直接依赖写进 `pyproject.toml`（声明"要什么"）；
- 锁文件提交进仓库（记录"装了哪一套"）；
- **CI 里用锁文件安装**（`uv sync --frozen`），杜绝"本地能跑，CI 挂"。

**加分项**：Agent 项目依赖冲突是重灾区——langchain / langgraph / 各家 SDK 版本咬合、`pydantic v1/v2` 不兼容；讲一次你被传递依赖坑过（比如 pydantic 版本冲突）并靠锁文件/`uv tree` 解决的经历，比讲概念有用。

---

### 16. pytest：fixture 与打桩
**真实问法**："fixture 和 monkeypatch 是干什么的？怎么测一个会调用外部 API 的函数？"

**考察点**：测试能力，AI 时代"评审 + 测试兜底"是岗位硬要求。

**参考答案**：

- **fixture**：管理测试的**前置与后置**（setup/teardown）和共享数据——临时目录、数据库连接、配置对象；`yield` 之前是准备，之后是清理（复用上下文管理器思想）：

```python
import pytest

@pytest.fixture
def kb():
    store = create_temp_store()
    yield store          # 测试用
    store.cleanup()      # 测试后清理
```

- **monkeypatch**：在测试里**临时替换**外部依赖（属性、环境变量、函数），测试结束自动还原。

测"调用外部 API"的函数，铁律是**不真发请求**——把 HTTP/LLM 客户端换成假实现，断言两件事：**传进去的参数对不对**、**对假返回的处理对不对**：

```python
def test_call_llm(monkeypatch):
    captured = {}

    class FakeClient:
        def chat(self, prompt):
            captured["prompt"] = prompt
            return "假回答"

    monkeypatch.setattr(module, "client", FakeClient())   # 打桩
    result = module.call_llm("你好")
    assert result == "假回答"
    assert "你好" in captured["prompt"]                    # 入参被正确传递
```

这样测试**不依赖网络、不花钱、可重复**，还顺带验证了调用参数。

**加分项**：Agent 的评测集/回归测试 = "固定输入 + 打桩外部依赖（LLM/检索/工具）"；把 `pytest` 用在 Agent 链路测试上，直接命中面试官关心的"AI 时代怎么保证质量"。

---

### 17. AI 生成代码的 Review 清单
**真实问法**："现在代码大量是 AI 写的，你 Review 时会重点看什么？"

**考察点**：可维护性意识（呼应第十五章导读"AI 写代码，你签字负责"）。

**参考答案**：

AI 生成代码的典型问题是"表面正确、细节藏雷"，我的 Review 清单按优先级：

1. **类型与签名**：标注是否完整？`Any` 泛滥的地方往往是没想清楚；
2. **纯函数化**：有没有隐藏的副作用？同一个函数被调两次结果是否一致？状态是否被悄悄改掉（深浅拷贝坑）；
3. **依赖注入**：客户端（LLM/DB/HTTP）是不是在函数体里硬编码 `Client()`？应该是从参数/配置注入，否则没法测试；
4. **错误处理**：有没有 `except:` 裸捕获吞异常？失败路径有没有日志？超时/重试/降级有没有兜底？
5. **边界条件**：空输入、`None`、默认参数（可变默认参数！）、并发下共享状态；
6. **可观测性**：日志分级是否清晰、关键决策有没有记录（Agent 里尤其要留 Trace）。

一句话：**AI 生成代码的审查重点是"它以为对的、但你的领域里是错的"**——业务规则、安全边界、成本约束，这些是模型看不见的。

**加分项**：把这套清单沉淀成仓库里的 `REVIEW_CHECKLIST.md` 或 `AGENTS.md`，并讲一个"AI 代码里藏 bug 被我 Review 抓出来"的真实例子——这比任何空话都有说服力。

---

### 18. dict 与 set 的底层
**真实问法**："`dict` 的 key 有什么要求？为什么 `list` 不能当 key？`set` 怎么判重？"

**考察点**：哈希表机制，很多人只会用不会说。

**参考答案**：

`dict` 和 `set` 底层都是**哈希表**，平均 O(1) 查找。两个硬性要求：

1. **key 必须可哈希**：可哈希 ≈ 不可变（`__hash__` 不为 `None`）。`list` 可变、哈希值会变，所以 `__hash__` 是 `None`，不能当 key；`tuple` 可哈希（除非里面装了 list）。
2. **哈希稳定性**：对象放进 dict/set 后，**它的哈希值不能变**，否则"放进去了却找不到"。

为什么可变对象哈希会导致 bug：

```python
class Point:
    def __init__(self, x, y):
        self.x, self.y = x, y
    def __hash__(self): return hash((self.x, self.y))
    def __eq__(self, other): return (self.x, self.y) == (other.x, other.y)

p = Point(1, 2)
s = {p}
p.x = 99               # 哈希值变了！
# 但它在哈希桶里的位置还是按旧哈希放的 → s 里查不到它了
```

自定义对象进 set/dict 的规矩：**同时实现 `__hash__` 和 `__eq__`，且哈希所依赖的字段在生命周期内不可变**（hash 与 eq 语义要一致）。

深一层：CPython 的字符串哈希带**随机化种子**（`PYTHONHASHSEED`），每次进程启动不同，是为了防哈希碰撞 DoS 攻击（历史上靠大量同哈希字符串拖垮 dict 的 CVE）。所以不要假设字符串哈希跨进程稳定。

**加分项**：Agent 里"上下文去重、记忆去重、缓存 key"全是哈希表应用；把"放进 set 后字段别改"讲成你踩过的缓存失效 bug，很加分。

---

## 四、两道开放题（最像真实面试的收尾）

### 19. "讲一个你印象最深的 Python 踩坑"
**考察点**：是不是真写过、真调试过，而不是背过八股。

**答题思路**：严格按"**现象 → 定位 → 根因 → 修复 → 防再犯**"五段讲，控制在 2 分钟内。下面是可变默认参数的**示范答案模板**（可直接套用你的真实经历）：

> "最深的坑是可变默认参数。**现象**：我给工具函数加了个缓存参数，某天发现两个用户问同样的问题，第二个用户直接拿到了第一个用户的**私人答案**。**定位**：先查了调用处没问题，再查函数签名，发现 `def ask(user, cache=[]):`。**根因**：`[]` 在函数定义时只创建一次，所有调用共享同一个 list，多用户数据混在一起了。**修复**：改成 `cache=None` 加空判断，并在函数内新建列表。**防再犯**：我把这条写进了团队的 Review 清单，凡是默认参数是可变对象的代码一律打回。"

候选题材任选：可变默认参数、深浅拷贝串数据、闭包延迟绑定、`except:` 吞掉异常、async 里调阻塞函数卡死。

**加分项**：如果这个坑发生在你做的 **Agent 项目**里（比如工具状态被共享污染、多租户串数据），可信度翻倍——面试官要的不是段子，是"你踩过、且知道怎么防"。

---

### 20. "AI 都能写代码了，Python 基础还有必要学吗？"
**考察点**：对 AI 时代的认知（呼应本章开篇的立场）。

**答题思路**：给一个**有立场、有结构、有例证**的回答，不要和稀泥：

> "有必要，而且更值钱了。AI 生成代码把'从零写'的**速度**打没了，但没把'判断代码对不对、把代码接进系统、出问题时兜底'这三件事打没。第一，**评审**：AI 写的深浅拷贝、异常吞掉、并发共享状态这些 bug 非常典型，看不懂底层机制就发现不了；第二，**接入**：把 AI 生成的工具函数接进 asyncio 的 Agent 循环、接进 pytest 测试体系、接进锁文件管理，靠的还是基本功；第三，**兜底**：线上出问题，最后签字的还是人。所以 AI 时代 Python 基础从'会不会写'变成了'能不能看懂并负责'——门槛没消失，只是上移了。"

**加分项**：举一个"AI 生成的代码里藏着 bug，被你用基础能力 Review 出来"的真实案例（呼应第 17 题的 Review 清单），胜过任何口号。

---

- 返回 [第十五章导读](./README.md)
