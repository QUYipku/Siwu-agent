"""PyInstaller runtime hook — 修复 tiktoken Rust 扩展在冻结环境中的加载"""
import os
import sys

# tiktoken 的 Rust 扩展通过 tiktoken_ext 命名空间包加载
# PyInstaller 可能漏掉这个文件，需要显式添加路径
if getattr(sys, 'frozen', False):
    # 在 sys._MEIPASS 中查找 tiktoken 数据
    meipass = sys._MEIPASS
    # 确保 tiktoken_ext 可导入
    tiktoken_ext_path = os.path.join(meipass, 'tiktoken_ext')
    if os.path.isdir(tiktoken_ext_path) and tiktoken_ext_path not in sys.path:
        sys.path.insert(0, tiktoken_ext_path)

    # 同样处理 tiktoken 模型文件
    for root, dirs, files in os.walk(meipass):
        for d in dirs:
            if d == 'tiktoken_ext':
                full = os.path.join(root, d)
                if full not in sys.path:
                    sys.path.insert(0, full)
