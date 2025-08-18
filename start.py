#!/usr/bin/env python3
"""
启动脚本：带有更多配置选项的启动器
"""

import argparse
import sys
import os
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="飞常准MCP代理服务启动器")
    parser.add_argument("--host", default="0.0.0.0", help="服务主机地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="服务端口 (默认: 8000)")
    parser.add_argument("--accounts-file", default="accounts.txt", help="账号文件路径 (默认: accounts.txt)")
    parser.add_argument("--reload", action="store_true", help="启用热重载 (开发模式)")
    parser.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"], 
                       help="日志级别 (默认: info)")
    
    args = parser.parse_args()
    
    # 检查账号文件是否存在
    if not Path(args.accounts_file).exists():
        print(f"❌ 错误: 账号文件 '{args.accounts_file}' 不存在")
        print("💡 请确保账号文件存在，每行格式为: username|password|sk-token")
        sys.exit(1)
    
    # 设置环境变量
    os.environ["ACCOUNTS_FILE"] = args.accounts_file
    
    print(f"🚀 启动飞常准MCP代理服务...")
    print(f"📡 服务地址: http://{args.host}:{args.port}")
    print(f"📄 账号文件: {args.accounts_file}")
    print(f"📊 日志级别: {args.log_level}")
    print("=" * 50)
    
    # 导入并启动服务
    try:
        import uvicorn
        from main import app
        
        uvicorn.run(
            "main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=args.log_level
        )
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print("💡 请先安装依赖: pip install -r requirements.txt")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 服务已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()