# -*- coding: utf-8 -*-
"""restart_agh.py — AGH 全清冷启动(排障剧本固化, 队长 · 系统集成线)

实测教训(10/9 三次复现): 杀 MCP 行 python 或强杀守护进程后, 当前工作区的
会话游标会在 sessions.db 里坏掉, `agh -p` 全部报 "no turn/end row arrived
within 1000ms", 优雅 `daemon restart` 无效。唯一可靠流程 = 杀干净 → serve
冷启动 → 等 MCP 行 python 就绪 → 再跑批(必要时换 .agh_ws 工作区目录)。

本脚本固化该流程:
    1) 杀所有命令行含 agnes 的 node 进程 + 含 mcp_tools 的 python 进程
    2) 后台起 `agnes.mjs serve`(Web 127.0.0.1:4177, 日志 serve.log)
    3) 等端口监听 + 行 python 就绪(最多 180s)
    4) --probe 时再跑 `doctor provider --probe` 确认 Provider 配置仍在

用法: python -I restart_agh.py [--probe]
退出码: 0 = 就绪; 1 = 未就绪
"""
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
NODE = r"D:\KS\node.exe"
AGH = r"C:\Users\TEMP\Desktop\agnes-harness\agnes-harness-main\packages\cli\dist\local\agnes.mjs"
PORT = 4177
LOG = HERE / "serve.log"
PS = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass"]


def ps_query(pattern: str) -> subprocess.CompletedProcess:
    """查 Name 为 node/python 且命令行匹配 pattern 的进程。只按 Name 过滤,
    避免把命令行里含 pattern 字样的 powershell/cmd 自己算进去。"""
    script = (
        "$p = @(Get-CimInstance Win32_Process | Where-Object { "
        "($_.Name -eq 'node.exe' -or $_.Name -eq 'python.exe' -or "
        f"$_.Name -eq 'pythonw.exe') -and $_.CommandLine -match '{pattern}' }}); "
        "$p.Count"
    )
    return subprocess.run(PS + ["-Command", script],
                          capture_output=True, text=True, errors="replace")


def ps_kill(pattern: str) -> int:
    """杀命令行匹配 pattern 的 node/python 进程, 返回杀掉的数量。"""
    script = (
        "$p = @(Get-CimInstance Win32_Process | Where-Object { "
        "($_.Name -eq 'node.exe' -or $_.Name -eq 'python.exe' -or "
        f"$_.Name -eq 'pythonw.exe') -and $_.CommandLine -match '{pattern}' }}); "
        "$p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
        "-ErrorAction SilentlyContinue }; $p.Count"
    )
    r = subprocess.run(PS + ["-Command", script],
                       capture_output=True, text=True, errors="replace")
    out = (r.stdout or "").strip()
    return int(out) if out.isdigit() else 0


def count_proc(pattern: str) -> int:
    out = (ps_query(pattern).stdout or "").strip()
    return int(out) if out.isdigit() else -1


def port_open(port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    probe = "--probe" in sys.argv

    print("[1/4] 清理残留进程 ...")
    n = ps_kill("agnes") + ps_kill("mcp_tools")
    print(f"      已杀 {n} 个匹配进程(agnes 相关 node / mcp_tools python)")
    time.sleep(3)
    left = count_proc("agnes") + count_proc("mcp_tools")
    if left > 0:
        print(f"      警告: 仍有 {left} 个匹配进程残留(可能权限不足), 继续 ...")

    print("[2/4] 后台启动 serve (127.0.0.1:4177) ...")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n===== restart_agh.py {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    subprocess.Popen(
        [NODE, AGH, "serve"],
        cwd=str(HERE),
        stdout=open(LOG, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.CREATE_NO_WINDOW,
    )

    print("[3/4] 等服务就绪(端口 + MCP 行 python) ...")
    deadline = time.time() + 180
    web_ok = row_ok = False
    while time.time() < deadline:
        web_ok = port_open(PORT)
        row_ok = count_proc("mcp_tools") > 0
        if web_ok and row_ok:
            break
        if not web_ok:
            print(f"      端口未开, {int(deadline - time.time())}s 后超时 ...")
            time.sleep(5)
        elif not row_ok:
            print("      端口已开, 等 MCP 行 python 出现 ...")
            time.sleep(2)
    print(f"      Web {'✓' if web_ok else '✗'}  行 python {'✓' if row_ok else '✗'}")
    if not (web_ok and row_ok):
        print("未完全就绪。若行 python 始终不出现, 检查 Web 里 MCP 注册状态;")
        print("tail serve.log 看守护进程日志。")
        return 1

    if probe:
        print("[4/4] Provider 探针 ...")
        r = subprocess.run([NODE, AGH, "doctor", "provider", "--probe"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=90)
        print(r.stdout[-800:] or r.stderr[-800:])
        if r.returncode != 0:
            print("探针未通过(rc!=0), 到 Web 检查 Provider 配置。")
            return 1
    print("就绪。跑批: python -I batch_agh.py (--only <id> 单题重跑)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
