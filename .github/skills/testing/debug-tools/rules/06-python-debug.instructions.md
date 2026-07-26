---
applyTo: '**/*.{py}'
---

# Python Debug Rules

> **AI Summary**: Python 调试：mypy/pyright 类型检查→pytest→pdb→cProfile。

策略：**类型标注 + logging + pdb + 最小复现**。

## 调试脚本

```powershell
# ── 类型检查 ──
mypy src/ --strict                                   # mypy 严格
mypy src/suspected_module.py --strict                # 指定文件
mypy src/ --check-untyped-defs                       # 宽松
pyright src/                                         # pyright（更快）

# ── Lint ──
ruff check src/                                      # ruff（超快）
pylint src/
flake8 src/

# ── 测试 ──
python -m pytest                                     # 全部
python -m pytest tests/test_suspected.py -v          # 指定文件
python -m pytest tests/test_suspected.py::test_function -v  # 指定函数
python -m pytest -s tests/test_suspected.py          # 显示 stdout
python -m pytest --pdb tests/test_suspected.py       # 失败进 pdb
python -m pytest --cov=src/ --cov-report=html        # 覆盖率

# ── 调试器 ──
# breakpoint()  # Python 3.7+ 内置
python -m pdb src/script.py                          # 脚本进 pdb
python -m pytest --pdb -x tests/test_suspected.py    # pytest + pdb

# ── 性能分析 ──
python -m cProfile -o profile.prof src/script.py     # cProfile
python -m pstats profile.prof                         # 查看报告
pip install line_profiler && kernprof -l -v src/script.py  # 逐行
pip install memory_profiler && python -m memory_profiler src/script.py  # 内存

# ── 依赖检查 ──
pip list --outdated                                  # 过时包
pipdeptree                                           # 依赖树
pip check                                            # 冲突
```

## 常见问题与排查

### 类型标注错误

```python
reveal_type(some_variable)  # mypy 输出推断类型
from typing import cast; result = cast(ExpectedType, some_value)  # 明确类型
from typing import TypedDict
class Config(TypedDict):
    host: str
    port: int
    debug: bool
```

### None 相关错误

```python
if obj is not None and obj.attr is not None:  # 安全访问
from typing import Optional
def get_user(id: int) -> Optional[User]: ...
# DEBUG: [function] obj=%s, isNone=%s
```

### 异常处理

```python
try:
    risky_operation()
except SpecificError as e:
    # DEBUG: [function] SpecificError=%s
    raise
except Exception as e:
    # DEBUG: [function] unexpected error=%s
    raise
```

### asyncio

```python
import asyncio
async def debug_async():
    # DEBUG: [debug_async] start | args=%s
    await asyncio.sleep(0)
    # DEBUG: [debug_async] resumed
try:
    result = await asyncio.wait_for(coro(), timeout=5.0)
except asyncio.TimeoutError:
    # DEBUG: [function] timeout
    pass
```

### 内存泄漏

```python
import tracemalloc
tracemalloc.start()
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)  # DEBUG: [memory] %s
```

### 导入/模块

```powershell
python -c "import sys; print('\n'.join(sys.path))"                        # 模块搜索路径
python -c "import suspected_module; print(suspected_module.__file__)"     # 模块位置
```

# 检查循环导入
python -X importtime src/script.py 2> import-time.log
```

## 打点规范

```python
# 1. print 打点（快速验证，定位后清理）
# DEBUG: print(f"[function] enter: input={input}")
# DEBUG: print(f"[function] exit: result={result}")

# 2. logging 打点（可分级控制，适合保留）
import logging
logger = logging.getLogger(__name__)
# DEBUG: logger.debug(f"[function] detail: {value}")
# logger.info(f"[function] info: {value}")

# 3. traceback 打点（获取完整调用栈）
import traceback
# DEBUG: traceback.print_stack()  # 打印当前调用栈
# DEBUG: traceback.print_exc()   # 打印异常回溯

# 4. inspect 打点（获取调用者信息）
import inspect
# DEBUG: caller = inspect.currentframe().f_back.f_code.co_name
```

## 最小复现脚本模板

```python
"""
最小复现脚本 — debug_repro.py
用法: python debug_repro.py
"""
import sys
import traceback

# 1. 最小输入数据
INPUT = {
    "key": "value",
    # 逐步删除字段直到问题消失
}

# 2. 预期行为
EXPECTED = {"status": "ok"}

# 3. 调用目标代码
def main():
    try:
        result = some_function(INPUT)
        assert result == EXPECTED, (
            f"Mismatch:\n"
            f"  expected: {EXPECTED}\n"
            f"  got:      {result}"
        )
        print("PASS: behavior matches expected")
    except Exception:
        print("FAIL: exception raised")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
```

## 调试流程

```
① mypy src/ --strict → 修复类型错误
② ruff check src/ → 修复 lint 问题
③ python -m pytest tests/ -v → 确认测试通过
④ 运行时异常：插入 breakpoint() → pdb 交互式调试
⑤ 逻辑问题：编写最小复现脚本隔离验证
⑥ 性能问题：cProfile / line_profiler 定位热点
⑦ 修复后：mypy + ruff + pytest 回归验证
```

### 常用 pdb 命令速查

| 命令           | 缩写       | 作用                     |
| -------------- | ---------- | ------------------------ |
| `list`         | `l`        | 显示当前行附近代码       |
| `next`         | `n`        | 执行下一行（不进入函数） |
| `step`         | `s`        | 进入函数内部             |
| `continue`     | `c`        | 继续执行到下一个断点     |
| `print expr`   | `p expr`   | 打印表达式值             |
| `pp expr`      | `pp`       | 漂亮打印表达式值         |
| `args`         | `a`        | 打印当前函数参数         |
| `where`        | `w`        | 打印调用栈               |
| `up`           | `u`        | 向上移动栈帧             |
| `down`         | `d`        | 向下移动栈帧             |
| `break lineno` | `b lineno` | 在指定行设置断点         |
| `quit`         | `q`        | 退出调试器               |
